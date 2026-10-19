# Procedures (toolkit calls, in order)

Each procedure names the calls it runs and its status. "Verified live" means `test_mockup_live.py`
runs those calls on Photoshop 27.11 (macOS), on a 1000x800 fixture of gray strips (luminance 60
to 230) under a printable quad. "Not tested" means the block was written from the toolkit's code and
Adobe's documentation but never run as shown. Every call is one ExtendScript job through `ps_run`:
read the error after each one.

Scenario steps appear as comments. They go through the Scenario MCP with the `scenario` skill
(connection, `recommend`, the price quote and the user's yes before every paid Scenario job, job
waiting), `scenario-product-shots` (plates and packshots), `scenario-image-editing` (background
removal, vectorize, upscale) and `scenario-brand-kit` (vector marks).

Setup for every block:

```python
import json, os, sys
sys.path.insert(0, "<skills>/scenario-photoshop-mockups/scripts")
import ps_mockup as M             # also puts scenario-photoshop-expert/scripts on the path
import ps_run, ps_gates as G, ps_review as R, ps_audit as A, ps_io as IO
OUT = "/path/to/a/work/folder"    # never the folder of the user's PSD
DOC = "tote_shoot.psd"            # the document the brief names

def history():
    js = "var h = app.activeDocument.historyStates; return [h.length, app.activeDocument.activeHistoryState.name];"
    return ps_run.run(js)["result"]

def check_doc():
    assert A.doc_state()["name"] == DOC, "another document is active"
```

Layer arguments take a layer name or id. The placeholder's default name is "Place Design Here"; its
group is "Mockup: Place Design Here". Pass `name=` for a second face ("Front", "Side").

## P0. Session, brief, route

Status: `doc_state` is a lead call, tested by the lead's suite.

```python
s = A.doc_state()
assert s["name"] == DOC, s["name"]
print(s["width"], s["height"], s["mode"], s["profile"])
for L in s["layers"]:                 # top level; groups hold their own "layers"
    print(L["kind"], L["path"], L["bounds"])
h0 = history()
```

Route by the brief:

- **Flat face, one or many designs** (tote, box, bag, poster, screen): P1, P2, P3, P5, P6 or P7,
  P10, P11.
- **Curved face** (can, bottle, mug): P1, then the curved warp by hand
  ([gui-paths.md](gui-paths.md)), then P5 and P6. Do not run `fit_quad` on it afterwards.
- **A Scenario result onto a screen or frame:** P8, then P5 if the surface has texture.
- **A logo that exists only as a small raster:** P9 before P6.

The product layer must be a pixel layer or a smart object. Lighting from a Background layer is not
tested: duplicate it first (Layer > Duplicate Layer, or Cmd-J) and name the copy "Product".

## P1. The printable area

Status: not tested by script (the live test made a rectangular selection). Select Subject by Action
Manager is measured on 27.11.

```python
js = """
var d = app.activeDocument;
d.activeLayer = d.artLayers.getByName("Product");
var desc = new ActionDescriptor();
desc.putBoolean(stringIDToTypeID("sampleAllLayers"), false);
executeAction(stringIDToTypeID("autoCutout"), desc, DialogModes.NO);
// leave out the lid and the base: subtract two rectangles (document px)
var lid = [[300, 120], [720, 120], [720, 190], [300, 190]];
var base = [[300, 600], [720, 600], [720, 680], [300, 680]];
d.selection.select(lid, SelectionType.DIMINISH);
d.selection.select(base, SelectionType.DIMINISH);
return 1;
"""
assert ps_run.run(js)["ok"]
IO.export_mask(OUT + "/area.png")         # white = printable; open it and look
print(IO.selection()["bounds"])
```

- A selection made by Select Subject covers the whole product. Subtract what is not printed: lid,
  base, seams, straps, handles, a hand holding it.
- For hard rims, ask the user for a Pen path and make a selection from it (Cmd-Return in the Paths
  panel). Geller draws the can's outline with the Curvature Pen for the same reason (Geller
  [0l2Ma_2B-A8 00:32]).
- A cutout from `scenario-image-editing` (background removal) can be placed as a layer; Cmd-click
  its thumbnail loads its alpha as the selection.
- Keep the selection active for P3: `placeholder` turns it into the group mask.

## P2. The four corners

Status: not tested. The toolkit takes the corners as data; it does not find them.

The quad is `[[x, y] TL, TR, BR, BL]` in document pixels: the corners of the printed area as the
camera sees them.

From a 4-point path the user drew (the most reliable source):

```python
js = """
var p = app.activeDocument.pathItems.getByName(%s), sp = p.subPathItems[0], pts = [];
for (var i = 0; i < sp.pathPoints.length; i++) pts.push(sp.pathPoints[i].anchor);
return pts;
""" % json.dumps("Print area")
pts = ps_run.run(js)["result"]

def order(pts):                    # TL, TR, BR, BL from four points in any order
    top = sorted(sorted(pts, key=lambda p: p[1])[:2], key=lambda p: p[0])
    bot = sorted(sorted(pts, key=lambda p: p[1])[2:], key=lambda p: p[0])
    return [top[0], top[1], bot[1], bot[0]]

quad = order(pts)
```

- Path point coordinates can come back in points (1/72 inch) rather than pixels. If the quad is
  smaller than the face by the factor resolution / 72, multiply by it.
- The sort fails on a face rotated about 45 degrees. Check the order on a preview.

From previews, when there is no path: read approximate corners on a fit-to-screen
`R.preview(OUT + "/whole.png")` (scale back by the preview's ratio), then refine each one on a 100%
crop around it:

```python
for x, y in quad:
    R.preview(OUT + "/corner_%d_%d.png" % (x, y), crop=[x - 60, y - 60, x + 60, y + 60], max_px=0)
```

Real proportions: measure the printed area's real width and height (the brief, a dieline, or a
straight-on photo) and pass them as `size` in P3. GraphiqVibe starts a box mockup from "the size
that we used for the design" (GraphiqVibe [WeDJv63Wgjk 01:37]); WeJustClickme measures the can first
(WeJustClickme [-VM3ee1O_8U 00:00]). Without it, `quad_size(quad)` uses the mean edge lengths, which
are foreshortened.

## P3. Placeholder

Status: verified live (tests 1 and 7). Corners within 1 px, `fit_check` under 0.5, one History state
named "Scenario: Mockup placeholder", Fill 60, `size` equal to `quad_size(quad)`, the rendered red
checked 5 px inside and outside each corner. With a selection active, `group_mask` true and red only
inside the selection. `size=` and `color=` are not tested.

```python
check_doc()
quad = [[300, 200], [700, 240], [690, 600], [310, 560]]
P = M.placeholder(quad, name="Place Design Here", size=[800, 500])   # size: real ratio
print(P["group"], P["size"], P["corner_error"], P["fit_check"], P["group_mask"])
assert P["corner_error"] < 1.0 and P["fit_check"] < 0.5
assert history()[0] == h0[0] + 1
for x, y in quad:
    R.preview(OUT + "/fit_%d_%d.png" % (x, y), crop=[x - 40, y - 40, x + 40, y + 40], max_px=0)
```

- The placeholder is a solid color (default red) so its edges read against any product. Fill 60 lets
  the product show through while fitting, as builders lower opacity or Fill (Quick Fix Up
  [boONV-waIUk 00:33]; WeJustClickme [-VM3ee1O_8U 01:06]).
- `mask_selection=False` ignores an active selection.
- Open each corner crop: the red edge meets the face's corner, with no gap and no overlap past the
  rim.

## P4. Re-fit and read the corners

Status: verified live (test 2): a second quad on the warped placeholder, `reset` true, `wrapped`
false, the same error thresholds, `corners` `consistent` true.

```python
quad2 = [[340, 180], [720, 260], [660, 620], [280, 540]]
F = M.fit_quad("Place Design Here", quad2)
print(F["reset"], F["wrapped"], F["corner_error"], F["fit_check"])
C = M.corners("Place Design Here")
print(C["corners"], C["consistent"], C["size"], C["fill"])
```

- `fit_quad` resets any warp first (`warpNone`), so a hand-made curve is lost. Re-fit before a hand
  curve, never after.
- `corner_error` is the largest distance from a corner to its target; `fit_check` compares the
  stored warp with the quad's box, without pixels.
- Move one corner a few pixels at a time and re-fit until the corner crops agree.

## P5. Test design, lighting, creases

Status: `lighting` verified live (test 4): a flat gray design got darker by more than 15 over a dark
strip of the product and brighter by more than 5 over a bright one; outside the design the image
stayed within 4 of its luminance; one History state. `displace` verified live (test 5) at
`scale=100` with an explicit `map_dir` and the default blur: the map file exists, one History state,
a straight line in the design bent differently at two places. `prefix=`, the default map folder and
lighting from a Background layer are not tested.

Make a test design at the placeholder's content size (Pillow), with a gray ramp and a grid:

```python
from PIL import Image, ImageDraw
w, h = M.corners("Place Design Here")["size"]
ramp = Image.new("RGB", (w, h))
d = ImageDraw.Draw(ramp)
for x in range(w):
    v = int(255 * x / max(1, w - 1))
    d.line([(x, 0), (x, h)], fill=(v, v, v))
for x in range(0, w, 40):
    d.line([(x, 0), (x, h)], fill=(220, 40, 40))
for y in range(0, h, 40):
    d.line([(0, y), (w, y)], fill=(220, 40, 40))
ramp.save(OUT + "/ramp.png")

M.replace_design("Place Design Here", OUT + "/ramp.png", fit="exact")
Lt = M.lighting("Place Design Here", "Product")
print(Lt["neutral"], Lt["layers"], Lt["product_under_design"]["luminance"])
D = M.displace("Place Design Here", "Product", scale=8, map_dir=OUT + "/maps")
print(D["map"], D["map_box"], D["blur"], D["scale"])
assert os.path.exists(D["map"])
R.preview(OUT + "/ramp_lit.png")
```

- `lighting` measures the product's mean luminance under the design (`neutral`). The "Shading
  (product)" copy is Multiply with Levels 0 to `neutral`: only what is darker than the mean darkens.
  The "Highlights (product)" copy is Screen with Levels `neutral` to 255: only what is brighter
  lightens. Both are desaturated and clipped above the top of the design's clipping chain.
- Lower `shade` or `light` (percent opacity) when the fabric reads heavier than the photo; set one
  to 0 to skip that copy.
- `displace` crops the product's pixels to the design's bounds, desaturates and blurs them, saves
  the map as a PSD, and applies Displace as a Smart Filter (Stretch To Fit, Repeat Edge Pixels).
  Default blur: max(1, document width / 1500). Without `map_dir`, the map goes in "<document> maps/"
  next to a saved document, else in Documents/Scenario Photoshop/displace maps/.
- Scale is in pixels of displacement. Start at the toolkit's 8 and look; experts used 4 on a 4000
  px-wide fabric scene, 15 on a crushed can, 10 to 20 on a t-shirt (Dinda [_VNqOhHJIm8 06:11];
  Geller [0l2Ma_2B-A8 05:24]; Dinda [sy1w5mTif-E 06:27]).
- Re-running `displace` adds a second filter. Step back History first to change the scale.
- Look at the ramp: the grid lines bend along the folds, the dark end still shows the highlights,
  the bright end still shows the shadows. If one end goes flat, adjust that copy's opacity.

## P6. Replace the design

Status: verified live (test 3) with `fit="exact"`: `drift` under 0.5, `content_size` unchanged, Fill
back to 100, one History state, a left/right two-color design keeps its orientation. `cover` is run
in tests 4 and 6. `contain` is not tested.

```python
r = M.replace_design("Place Design Here", "/path/to/design.png", fit="cover")
print(r["content_size"], r["source_size"], r["scale"], r["drift"], r["fill"])
assert r["drift"] < 0.5
```

- `cover` scales the file to fill the content size and crops the overflow, centered; `contain` pads
  it (transparent) to fit inside; `exact` stretches it.
- The layer keeps its name; Photoshop's own Replace Contents would rename it after the file.
- The lighting copies and the Displace filter stay; the new design takes them on re-render. With the
  map deleted, this call fails with "the file was not found": re-run P5's `displace`.
- `reset_fill=False` keeps the fitting Fill, for a quick check before the final design.

## P7. Batch: one export per design

Status: verified live (test 6) with two designs: each PNG shows its own design's color, the document
renders identically before and after (difference 0), and the active History state is restored.

```python
designs = ["/designs/sunrise.png", "/designs/wave.png", "/designs/logo_on_white.png"]
h1 = history()
res = M.batch("Place Design Here", designs, OUT + "/mockups", fit="cover")
for r in res:
    print(os.path.basename(r["out"]), r["drift"])
assert history() == h1
R.sheet([r["out"] for r in res], OUT + "/mockups sheet.jpg",
        labels=[os.path.basename(r["design"]) for r in res])
```

- Each design is one History state named "Scenario: Batch design", exported from a merged temporary
  copy, then stepped back. Deleting a snapshot instead would send the document to its opening state.
- Output names are "<design file stem> mockup.png", at the document's full size.
- Plates from different photos give the same design at different apparent sizes; Stanik's second mug
  came out "way smaller" (Stanik [QTS-IWB3MKY 13:35]). Batch one plate at a time.

## P8. A placed Scenario result on four corners

Status: verified live (test 8): a result placed with `IO.place(..., fit="contain")`, then
`fit_quad`, gives `wrapped` true, `fit_check` under 0.5 and `corner_error` under 1.

```python
# Scenario MCP: the screen art, poster or label from the image skill; download to OUT
p = IO.place(OUT + "/screen_art.png", "Scenario result", bounds=[50, 50, 450, 300], fit="contain")
screen = [[412, 188], [868, 210], [860, 470], [405, 452]]
F = M.fit_quad("Scenario result", screen)
print(F["wrapped"], F["id"], F["corner_error"], F["fit_check"])
```

- A smart object placed from a file stores its warp in content pixels and lands about 10 px off.
  `fit_quad` wraps it once in a new smart object (`wrapped` true, a new `id`); use the new id.
- For a screen, skip `lighting` and `displace`, or use a light `shade`, since a screen emits light.
  A glossy screen may want a reflection layer by hand.
- Use P3's `placeholder` instead when several results will follow: one fit, then `batch`.

## P9. A logo for print

Status: not tested.

```python
# Scenario MCP, quoted first, with the user's yes:
#   scenario-image-editing: vectorize the raster logo (recommend with the user's words)
#   or scenario-brand-kit: trace an existing mark to editable SVG, do not regenerate it
#   asset_get the result; save its url with curl -L (asset_download returns a raster)
import subprocess
size = M.corners("Place Design Here")["size"]
subprocess.run(["rsvg-convert", "-w", str(size[0] * 2), "-o", OUT + "/logo.png",
                OUT + "/logo.svg"], check=True)    # librsvg; any SVG renderer works
```

- Render at least the placeholder's content size; twice that costs nothing and survives a later
  larger placeholder.
- Compare the trace with the original at 100%: letter shapes, counters, thin strokes, corners. A
  trace that changed a letter is redone, never patched in the mockup.
- Keep the SVG as the master. A recolor is a fill edit in the SVG, then a new render.
- Without a model: a large, clean, flat logo on white can be cut out by channel, which "keeps nice
  sharp edges" (Williams [tNrV1XdZX0o 00:31]); see [gui-paths.md](gui-paths.md). A small or blurry
  logo needs the vector.
- Brand color: Multiply under `lighting` keeps the color at the product's mean. Check the brand
  color on the sheet where the face is flat and evenly lit.

## P10. Hand finish

Status: not tested by script. The menu steps are in [gui-paths.md](gui-paths.md).

```python
js = """
var d = app.activeDocument;
var L = d.layerSets.getByName("Mockup: Place Design Here").artLayers.getByName("Place Design Here");
d.activeLayer = L;
L.applyGaussianBlur(1.0);       // on a smart object it is expected to land as a Smart Filter
return 1;
"""
print(ps_run.run(js, undo="Scenario: Ink blur"))
```

- If the call throws on the smart object, apply Filter > Blur > Gaussian Blur by hand
  ([gui-paths.md](gui-paths.md)).
- Check the Layers panel or a preview: the blur must sit above Displace in the Smart Filter list, so
  the design blurs after it bends (Dinda [_VNqOhHJIm8 07:17]).
- 1 px for fabric; 0.6 px when the design has a fine stroke (Dinda [_VNqOhHJIm8 08:55]).

## P11. Deliver

Status: `R.sheet` and `A.deliverable` are lead calls. `deliverable` is tested by the lead's suite;
`sheet` is not tested.

```python
print(A.deliverable("psd-handoff"))  # the active document, before a layered handoff; [] = pass
```

- Look at the sheet: every design, every corner, the printable edge.
- Report: the layer and group names, `corner_error` and `fit_check`, each design's `drift`, the map
  path (it must stay on disk while the filter exists), the output folder, and what was not verified.
