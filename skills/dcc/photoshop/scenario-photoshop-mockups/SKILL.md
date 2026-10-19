---
name: scenario-photoshop-mockups
description: "Use when putting a design, logo, label, pattern or Scenario result onto a product photo in Photoshop: a print, packaging or merchandise mockup on a tote, t-shirt, box, bag, can, bottle, mug, poster, phone or billboard screen, a product plate or lifestyle scene when there is no photo, a smart-object placeholder fitted to four corners or wrapped around a can or mug, swapping many designs into one mockup with one export per design, garment or product colorways, lighting and creases taken from the product photo (Multiply and Screen copies, Displace), masking the printable area, or a logo to vectorize. Also when a design looks pasted on, a dark garment swallows the design, a scripted warp misses its corners, Replace Contents comes back at the wrong size or renames the layer, Replace Contents fails with file not found after a Displace, or a batch export leaves the document changed."
license: MIT
---

# Product and brand mockups (Photoshop 2026)

Scenario supplies what the brief lacks: a product plate or a lifestyle scene when there is no photo,
a vector logo, new designs. Photoshop lands each one so it looks printed: a placeholder fitted to
the printable area, light and creases from the product's own pixels, one group mask, one export per
design or colorway. If a sibling skill named here is missing from your available skills, ask the
user to install it (`npx skills add scenario-labs/skills --skill <name>`); unattended, proceed from
tool schemas and flag the gap.

**REQUIRED BACKGROUND:** scenario-photoshop-expert (execution channel, round trip, gates).

**Status (2026-10-19):** every call in [`scripts/ps_mockup.py`](scripts/ps_mockup.py) is verified
live on Photoshop 27.11 (macOS): `test_mockup_live.py` runs 15 tests on striped and checkered
fixtures and on white and black shirts. Not tested: `fit="contain"`, `color=`, `prefix=`, the
default map folder, the shell commands, lighting from a Background layer, SVG placement, corners
read from a path, Windows, the Scenario jobs and the GUI paths.

## Stance (the expert delta)

- **Scenario makes what the photo lacks; the client's artwork stays a file.** Anders upscales a
  generated plate before placing the design (Anders [rrxTM5AZALU 00:34]). Hastie cleans the bottle
  with Generative Fill, then places the label "in SVG form" (Hastie [70L2ngS8raY 02:47]) as a smart
  object [70L2ngS8raY 03:21]. Existing artwork goes in through `replace_design`, never regenerated.
- **Build the placeholder first; the design goes in last.** Builders convert a rectangle to a smart
  object to "insert and edit your design non-destructively" (Quick Fix Up [boONV-waIUk 00:33]). Test
  it with "both bright and dark color" (Dinda [sy1w5mTif-E 01:38]): a ramp or check pattern, never
  the logo (Dinda [Z168F2BlAdA 15:36]).
- **Light comes from the product, relative to its own mean.** Multiply alone suits a bright tote
  (Dinda [_VNqOhHJIm8 04:35]). On a dark shirt, the dark slider makes the design disappear (Anders
  [rrxTM5AZALU 04:58]), so one builder splits light, midtone and shadow copies (Mockup Art
  [SKYL0FCOO04 15:12]). `lighting` darkens only below the product's mean and lightens only above.
- **Mask the printable area once, on the group.** Dinda moves the mask to the group "so that you
  don't have a copy of the same mask for multiple layers" (Dinda [_VNqOhHJIm8 02:22]). Can builders
  "leave out the lid and the lower part" (Quick Fix Up [boONV-waIUk 01:39]; WeJustClickme
  [-VM3ee1O_8U 02:22]). `placeholder` turns the active selection into the group mask.
- **Warp for the outline, Displace for the creases, and keep the map.** Geller warps a 4 by 4 mesh
  "without going inside the can", then displaces the label 15 px (Geller [0l2Ma_2B-A8 03:45];
  [0l2Ma_2B-A8 05:24]). [added] The Displace Smart Filter re-reads its map file, so `displace` keeps
  the map next to the document.
- **Round products wrap.** Cans and mugs take the Cylinder warp, bottle labels Arc Lower (Design
  Master [C3ZkcqB36xw 00:38]; Hastie [70L2ngS8raY 03:21]). [added] `fit_cylinder` scripts it:
  columns narrow toward the sides, and each edge bows by its own amount.
- **A fit is done when the corners measure right.** [added] Measured on 27.11: a scripted warp can
  return success and change nothing, or land up to 60 px off. `corner_error` and `fit_check` gate
  every fit. Hand builders check too (GraphiqVibe [WeDJv63Wgjk 06:13]).
- **A colorway shows the swatch and keeps the folds.** WeJustClickme clips a Solid Color layer in
  Color mode to a t-shirt (WeJustClickme [i-hYHLXDheU 02:10]). [added] Color mode keeps the
  garment's luminance: navy on a white shirt came out pale blue (measured). `colorways` moves the
  mid-tones to the swatch's luminance with Curves first, then measures the color.
- **Printed ink is never pin sharp.** "Whenever we print something on a piece of fabric like this,
  it is not that sharp" (Dinda [_VNqOhHJIm8 07:17]). On a dark shirt, Anders lowers the design to
  90% (Anders [rrxTM5AZALU 06:38]).

## Establish first

| Input            | Changes                                   | Default when silent                                          |
| ---------------- | ----------------------------------------- | ------------------------------------------------------------ |
| Product photo    | the plate under every design              | the open document; none: a Scenario plate or scene           |
| Product layer    | the pixels `lighting` and `displace` read | a pixel layer; duplicate a Background first                  |
| Surface          | `fit_quad` (flat) or `fit_cylinder`       | flat; cans, bottles and mugs take the cylinder               |
| Printable area   | the group mask                            | the face minus lid, base, seams and handles                  |
| Corners          | `quad`: TL, TR, BR, BL in document px     | the user's 4-point path, else read on 100% crops             |
| Real proportions | `placeholder(size=)`, kept in the layer   | the quad's mean edge lengths                                 |
| Designs          | `replace_design` or `batch`               | files on disk; an SVG rendered to PNG first                  |
| Colorways        | `colorways`, or a Scenario edit per color | none; names and hex values from the brief                    |
| Fit mode         | `cover`, `contain` or `exact`             | `cover`; `contain` keeps a logo's margins (untested)         |
| Output           | `batch` folder, delivery profile          | one PNG per design in a new folder; `psd-handoff` if layered |

## Workflow

Each call is one ExtendScript job through `ps_run`, with one named History state.
`import ps_mockup as M` puts the lead's `scripts/` on the path; then
`import ps_gates as G, ps_review as R, ps_audit as A, ps_io as IO`. Code:
[procedures](references/procedures.md).

1. **Intake.** `A.doc_state()`: name, size, mode, profile, layers. Name the product layer, each
   printable face, the designs and the colorways. A soft or small plate goes to
   scenario-photoshop-upscale-restore first. GATE: document named; product layer, surfaces, designs
   and colorways written.
2. **Scenario inputs.** Each Scenario job is quoted first, with the user's yes (`scenario`).
   - No product photo: a plate or scene from `scenario-image`; a product to restage or relight:
     `scenario-product-shots`; a fix on the photo: scenario-photoshop-generative-edit.
   - A logo: vectorize with `scenario-image-editing` or `scenario-brand-kit`. Save the SVG from
     `asset_get`'s `url` with `curl -L` (`asset_download` returns a raster), then render it to a PNG
     at least the content size (not tested).
   - New designs: `scenario-image` at the print ratio; repeats: `scenario-textures`. A material
     change (heather, wash): an instruction edit per color, `scenario-product-shots` (not tested).

   GATE: quote approved; outputs on disk; the vector matches the original at 100%, letters and
   counters included; plates of one set share one camera (Stanik [QTS-IWB3MKY 13:35]).

3. **Printable area.** Select the face: Select Subject or a cutout's alpha, minus the lid, base,
   seams and handles; the user's Pen path for hard rims. `IO.export_mask(OUT + "/area.png")` to
   look. GATE: the mask covers the face and stops at its edges.
4. **Placeholder and fit.** `P = M.placeholder(quad, size=[w, h])` makes a solid smart object in
   group "Mockup: Place Design Here", warped to the quad at Fill 60, with the selection as the group
   mask. `size` is the printed area's real size (GraphiqVibe [WeDJv63Wgjk 01:37]); it rides in the
   layer's XMP and sets the crop of every design. Re-fit with `M.fit_quad(layer, quad)`. A can,
   bottle or mug: `M.fit_cylinder(layer, quad, bulge, top_bulge=, angle=)`: the label's corners,
   each edge's sag at its middle in px, the visible arc in degrees. Read with `M.corners(layer)`.
   GATE: `corner_error` under 1, `fit_check` under 0.5, `group_mask` true when a selection was
   active, each corner (and a cylinder's bottom middle) seen on a 100% `R.preview(crop=)`.
5. **Light and creases.** Swap in a ramp or check design with
   `M.replace_design(layer, ramp, fit="exact")`. Then `M.lighting(layer, product)` and
   `M.displace(layer, product, scale=s)`. GATE: folds and highlights show across both the ramp's
   dark and bright ends; `map` exists on disk and goes in the report.
6. **Designs.** `M.replace_design(layer, path)` per design, or
   `M.batch(layer, designs, OUT + "/mockups")`. GATE: `drift` under 0.5 and `content_size` unchanged
   per design; one PNG per design; after a batch, `A.history_gate(h0) == []` with `h0 = A.history()`
   taken before it.
7. **Colorways.** Select the garment, then
   `M.colorways(product, {"navy": "#1e3278"}, OUT + "/colorways")`: per color, a Curves layer and a
   Solid Color fill in Color mode above the product, masked by the selection (else clipped), one
   PNG, one step back. GATE: per colorway `check["delta_e"]` 5 or less and `check["folds"]` 0.9 or
   more; print and background unchanged; `A.history_gate(h0) == []`.
8. **Hand finish (not tested).** Ink blur 0.6 to 1 px as a Smart Filter on the design, shadows
   desaturated where color seeps, 90% on a dark garment, a contrast Curves on top
   ([gui-paths](references/gui-paths.md)). GATE: at 100%, folds cross the design, highlights sit on
   it, and its edges are as soft as the material.
9. **Deliver.** `R.sheet(pngs, OUT + "/sheet.jpg")` for review; `A.deliverable(profile)` before a
   layered handoff. GATE: every design and colorway seen on the sheet; `A.deliverable` returns `[]`;
   the report names the map path, the gate numbers and what was not verified.

**A placed Scenario result** (screen art, a poster frame):
`IO.place(path, "Scenario result", bounds=b, fit="contain")`, then
`M.fit_quad("Scenario result", quad)`; use the returned `id` (every fit wraps a new smart object).
Gate as stage 4.

**Fit order.** Fit before `displace`: a fit refuses a layer with Smart Filters or a layer mask
(masks go on the group). A fit replaces any hand warp (`reset` true). Several faces take one
placeholder each. A tapered bottle or a pouch keeps the hand warp
([gui-paths](references/gui-paths.md)), after the last fit.

## Numbers

| Value                                                   | Relative to                     | Source                                          |
| ------------------------------------------------------- | ------------------------------- | ----------------------------------------------- |
| `corner_error` under 1 px, `fit_check` under 0.5 px     | the requested corners           | toolkit, verified live                          |
| `drift` under 0.5 px                                    | corners before Replace Contents | toolkit, verified live                          |
| Cylinder `angle` 120 degrees; `top_bulge` = `bulge`     | the label's visible arc         | toolkit default                                 |
| Fill 60 while fitting, 100 after a replace              | the placeholder                 | toolkit default                                 |
| Shading 85%, Highlights 50%                             | the two product copies          | toolkit default                                 |
| Displace scale 8; map blur max(1, doc width / 1500)     | the toolkit's defaults          | toolkit default                                 |
| Displace 4, map blur 1 px                               | a fabric tote                   | Dinda [_VNqOhHJIm8 06:11]; [_VNqOhHJIm8 05:39]  |
| Displace 15, map blur 3 px                              | a crushed can                   | Geller [0l2Ma_2B-A8 05:24]; [0l2Ma_2B-A8 01:04] |
| Displace 10, then 20; map blur 18 px for big folds only | a t-shirt                       | Dinda [sy1w5mTif-E 06:27]; [sy1w5mTif-E 05:54]  |
| Ink blur 1 px; 0.6 px with a stroke                     | the design                      | Dinda [_VNqOhHJIm8 07:17]; [_VNqOhHJIm8 08:55]  |
| Design opacity 90%                                      | a dark garment                  | Anders [rrxTM5AZALU 06:38]                      |
| Colorway Delta E 5 or less; folds 0.9 or more           | mid-tones vs swatch (CIE76)     | authoring-time                                  |

Toolkit thresholds are authoring-time, from striped and checkered fixtures: check them on your own
images. Expert values depend on pixel width, crease depth and material.

## Quality gates

- **Code:** after every fit, `corner_error` under 1 and `fit_check` under 0.5; `corners` returns
  `consistent` true. After every replace, `drift` under 0.5 and `content_size` unchanged.
  `A.history_gate(h0, undo) == []` per call. `lighting` returns two layers; `displace` returns a
  `map` that exists; `batch` and `colorways` return one `out` per item and pass
  `A.history_gate(h0)`; each colorway's `check` within Numbers.
- **Visual:** each corner at 100%; a cylinder's columns narrowing toward the sides; the ramp under
  light and creases; the printable edge (no design on a lid, seam or hand); each export on the
  sheet. Rubric: [critique](references/critique.md).

## Common mistakes

| Mistake                             | Looks like                                       | Fix                                               |
| ----------------------------------- | ------------------------------------------------ | ------------------------------------------------- |
| Design placed straight on the photo | each new design needs a new warp                 | a placeholder, then `replace_design`              |
| The logo as the test design         | light and creases fail on the next design        | a ramp or check design first                      |
| Multiply only, on a dark product    | the design sinks into the shadows                | `lighting`: Multiply below the mean, Screen above |
| Blend If read from the design layer | highlights follow the artwork, not the product   | product copies (Dinda [sy1w5mTif-E 09:11])        |
| Displace map deleted or moved       | Replace Contents: "the file was not found"       | keep the map folder; re-run `displace`            |
| A fit judged by eye                 | corners a few px off, or a warp that did nothing | `corner_error`, `fit_check`, corner crops         |
| Foreshortened `size`                | artwork squashed after a replace                 | the printed area's real size                      |
| A can label fitted with `fit_quad`  | a flat sticker on a round can                    | `fit_cylinder`                                    |
| A colorway in Color mode alone      | navy on a white shirt comes out pale blue        | `colorways`: Curves under the Color fill          |
| A raster logo enlarged              | soft edges, wrong letters                        | the SVG master, rendered at content size          |

## Handoffs

- **Receives** from scenario-photoshop-expert: routing and document state; from
  scenario-photoshop-compositing: a product placed in a scene that now needs its design; from
  scenario-photoshop-key-art: art to show on a product, a poster or a screen.
- **Delivers** a "Mockup: <name>" group, one PNG per design and per colorway, the gate numbers and
  the map path. Poster sizes and type go to scenario-photoshop-key-art; a product into a new scene
  to scenario-photoshop-compositing; the final audit to scenario-photoshop-expert.
- **Scenario siblings:** `scenario` (connection, `recommend`, price quote, Scenario job waiting),
  `scenario-image` (plates and scenes with no photo, new designs), `scenario-product-shots`
  (restaging, relighting, colorway sets), `scenario-image-editing` (background removal, vectorize,
  upscale), `scenario-brand-kit` (vector marks, logo variants), `scenario-textures` (seamless
  repeats).

## Photoshop 2026 notes

Measured on 27.11 (more in [expert-notes](references/expert-notes.md)):

- A custom warp lands on its points only when the object is scaled up from the box it was wrapped
  at; at that box or below, corners drift up to 60 px. Each fit wraps at 97% of the target's box.
- `warpNone` can leave a transform the next fit rejects; a re-fit flattens with an identity warp.
- Replace Contents keeps the transform and renames the layer after the file; `replace_design`
  handles both.
- The Color blend mode is `BlendMode.COLORBLEND`; `BlendMode.COLOR` throws.

## References

- [`references/expert-notes.md`](references/expert-notes.md): the measured toolkit behavior, each
  expert's method, disagreements and deciders. Load when a case is not covered above.
- [`references/procedures.md`](references/procedures.md): code per stage. Load before writing an
  ExtendScript job.
- [`references/critique.md`](references/critique.md): the rubric. Load at stages 4 to 9.
- [`references/gui-paths.md`](references/gui-paths.md): hand warps, Blend If, ink blur, logo cutouts
  and templates by menu, for the user or a computer-use agent.
- [`references/sources.md`](references/sources.md): videos, credentials, URLs, docs.
- [`scripts/ps_mockup.py`](scripts/ps_mockup.py): the toolkit (docstring lists every call), on top
  of the lead's scripts.
