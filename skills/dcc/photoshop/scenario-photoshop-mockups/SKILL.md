---
name: scenario-photoshop-mockups
description: "Use when putting a design, logo, label, pattern or Scenario result onto a product photo in Photoshop: a print, packaging or merchandise mockup on a tote, t-shirt, box, bag, can, bottle, mug, poster, phone or billboard screen, a smart-object placeholder fitted to four corners, swapping many designs into one mockup with one export per design, lighting and creases taken from the product photo (Multiply and Screen copies, Displace), masking the printable area, or a logo to vectorize before it goes on a product. Also when a design looks pasted on, a dark garment swallows the design, a scripted warp misses its corners or does nothing, Replace Contents comes back at the wrong size or renames the layer, Replace Contents fails with file not found after a Displace, or a batch export leaves the document changed."
license: MIT
---

# Product and brand mockups (Photoshop 2026)

Expert mockups build the stack before the design. A placeholder smart object is fitted to the
printable area, the product's own pixels supply the light and the creases, one group mask trims the
edges, and only then does the artwork go in, once per design. Photoshop does the placement, the
lighting and the exports. Scenario models supply what the photo lacks: a clean product plate, a
background removal, a vector logo. If a sibling skill named here is missing from your available
skills, ask the user to install it (`npx skills add scenario-labs/skills --skill <name>`);
unattended, proceed from tool schemas and flag the gap.

**REQUIRED BACKGROUND:** scenario-photoshop-expert (execution channel, round trip, gates).

**Status (2026-10-19):** every call in [`scripts/ps_mockup.py`](scripts/ps_mockup.py) is verified
live on Photoshop 27.11 (macOS). `test_mockup_live.py` runs 8 tests on a gray-striped product
fixture, plus a visual check on a generated tote photo. It covers `placeholder` with and without a
group mask, `fit_quad` (a re-fit and a placed Scenario result), `corners`, `quad_size`,
`replace_design` in `exact` and `cover`, `lighting`, `displace` and `batch`. Not tested:
`fit="contain"`, `size=`, `color=` and `prefix=`, the default map folder, the shell commands,
lighting from a Background layer, curved warps, SVG placement, corners read from a path, Windows.
GUI paths are not tested.

## Stance (the expert delta)

- **Build the placeholder first; the design goes in last.** Builders convert a rectangle to a smart
  object to "insert and edit your design non-destructively" (Quick Fix Up [boONV-waIUk 00:33]).
  Dinda tests with a placeholder of "both bright and dark color" (Dinda [sy1w5mTif-E 01:38]): a red
  squiggle passes in Multiply and fails in Screen [sy1w5mTif-E 02:10]. Test the stack with a ramp or
  check pattern, never the logo (Dinda [Z168F2BlAdA 15:36]).
- **Light comes from the product, relative to its own mean.** Multiply alone suits a bright tote:
  painting there "is only going to darken it" (Dinda [_VNqOhHJIm8 04:35]). On a dark shirt, the dark
  slider makes the design disappear (Anders [rrxTM5AZALU 04:58]), so one builder splits the product
  into light, midtone and shadow copies (Mockup Art [SKYL0FCOO04 15:12]). `lighting` darkens only
  below the product's mean under the design and lightens only above it.
- **Mask the printable area once, on the group.** Dinda moves the mask to the group "so that you
  don't have a copy of the same mask for multiple layers" (Dinda [_VNqOhHJIm8 02:22]). Can builders
  "leave out the lid and the lower part" (Quick Fix Up [boONV-waIUk 01:39]; WeJustClickme
  [-VM3ee1O_8U 02:22]). `placeholder` turns the active selection into the group mask.
- **Warp for the outline, Displace for the creases, and keep the map.** Geller warps a 4 by 4 mesh
  "without going inside the can", then displaces the label 15 px (Geller [0l2Ma_2B-A8 03:45];
  [0l2Ma_2B-A8 05:24]). Maps "look best when they are slightly blurred" [0l2Ma_2B-A8 01:04]. [added]
  Measured on 27.11: the Displace Smart Filter re-reads its map file, so a deleted map breaks the
  next Replace Contents. `displace` saves the map next to the document.
- **A fit is done when the corners measure right.** [added] Measured on 27.11: a scripted custom
  warp can return success and change nothing, and a smart object placed from a file warps about 10
  px off. `fit_quad` reports `corner_error` and a pixel-free `fit_check`; both gate every fit. Hand
  builders check too: "it's not placed properly", then adjust (GraphiqVibe [WeDJv63Wgjk 06:13]).
- **The artwork never goes through a model.** Hastie cleans the product with Generative Fill. Then
  the label goes on "in SVG form" (Hastie [70L2ngS8raY 02:47]), as a smart object "to not only
  switch out that artwork if it gets changed" [70L2ngS8raY 03:21]. Scenario makes the plate, the
  cutout or the vector; the real artwork goes in through `replace_design`.
- **Printed ink is never pin sharp.** "Whenever we print something on a piece of fabric like this,
  it is not that sharp" (Dinda [_VNqOhHJIm8 07:17]): blur the design 1 px, 0.6 px with a stroke
  [_VNqOhHJIm8 08:55]. On a dark shirt, Anders lowers the design to 90% so the fabric shows through
  (Anders [rrxTM5AZALU 06:38]).

## Establish first

| Input            | Changes                                   | Default when silent                                                  |
| ---------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| Product photo    | the plate under every design              | the open document, confirmed by name                                 |
| Product layer    | the pixels `lighting` and `displace` read | a pixel layer; duplicate a Background first                          |
| Surface          | flat (`fit_quad`) or curved (GUI warp)    | flat; a curve is warped by hand                                      |
| Printable area   | the group mask                            | the face minus lid, base, seams and handles                          |
| Corners          | `quad`: TL, TR, BR, BL in document px     | the user's 4-point path, else read on 100% crops                     |
| Real proportions | `placeholder(size=)`                      | the quad's mean edge lengths                                         |
| Designs          | `replace_design` or `batch`               | files on disk; an SVG rendered to PNG first                          |
| Fit mode         | `cover`, `contain` or `exact`             | `cover`; `contain` keeps a logo's margins (untested)                 |
| Output           | `batch` folder, delivery profile          | one PNG per design in a new folder; `psd-handoff` for a layered file |

## Workflow

Each call is one ExtendScript job through `ps_run`, with one named History state.
`import ps_mockup as M` puts the lead's `scripts/` on the path; then
`import ps_gates as G, ps_review as R, ps_audit as A, ps_io as IO`. Code:
[procedures](references/procedures.md).

1. **Intake.** `A.doc_state()`: name, size, mode, profile, layers. Name the product layer and each
   printable face. A soft or small plate goes to scenario-photoshop-upscale-restore first: "you will
   need to upscale your mockups before importing them into Photoshop" (Anders [rrxTM5AZALU 00:34]).
   GATE: document named; product layer, surfaces and designs written.
2. **Plate and logo (Scenario, optional).** Each Scenario job is quoted first, with the user's yes.
   - A clean or restaged plate: `scenario-product-shots`; a fix on the open photo:
     scenario-photoshop-generative-edit.
   - Background removal or vectorize: `scenario-image-editing`; a traced or native vector mark:
     `scenario-brand-kit`.
   - Connection, `recommend` and Scenario job waiting: `scenario`.
   - A traced SVG comes from `asset_get`'s `url` with `curl -L`; `asset_download` returns a raster.
   - Render the SVG to a PNG at least the placeholder's content size (not tested).

   GATE: quote approved; outputs on disk; the vector compared with the original at 100%, letters and
   counters included.

3. **Printable area.** Select the face: Select Subject or a cutout's alpha, minus the lid, base,
   seams and handles; the user's Pen path for hard rims. `IO.export_mask(OUT + "/area.png")` to
   look. GATE: the mask covers the face and stops at its edges.
4. **Placeholder and fit.** `P = M.placeholder(quad, size=[w, h])` makes a solid smart object in
   group "Mockup: Place Design Here", warped to the quad at Fill 60, with the selection as the group
   mask. Give `size` the printed area's real ratio, not the foreshortened one (GraphiqVibe
   [WeDJv63Wgjk 01:37]). Re-fit with `M.fit_quad(layer, quad)`; read with `M.corners(layer)`. GATE:
   `corner_error` under 1, `fit_check` under 0.5, `group_mask` true when a selection was active,
   each corner seen on a 100% `R.preview(crop=)`.
5. **Light and creases.** Swap in a ramp or check design with
   `M.replace_design(layer, ramp, fit="exact")`. Then `M.lighting(layer, product)` and
   `M.displace(layer, product, scale=s)`. GATE: folds and highlights show across both the ramp's
   dark and bright ends; `map` exists on disk and goes in the report.
6. **Designs.** `M.replace_design(layer, path)` per design, or
   `M.batch(layer, designs, OUT + "/mockups")`. GATE: `drift` under 0.5 and `content_size` unchanged
   per design; one PNG per design; after a batch, the History length and active state as before.
7. **Hand finish (not tested).** Ink blur 0.6 to 1 px as a Smart Filter on the design, shadows
   desaturated where color seeps, 90% on a dark garment, a contrast Curves on top
   ([gui-paths](references/gui-paths.md)). GATE: at 100%, folds cross the design, highlights sit on
   it, and its edges are as soft as the material.
8. **Deliver.** `R.sheet(pngs, OUT + "/sheet.jpg")` for review; `A.deliverable(profile)` before a
   layered handoff. GATE: every design seen on the sheet; `A.deliverable` returns `[]`; the report
   names the map path, the gate numbers and what was not verified.

**A placed Scenario result.** Screen art for a phone, a billboard or a poster frame:
`IO.place(path, "Scenario result", bounds=b, fit="contain")`, then
`M.fit_quad("Scenario result", quad)`. The toolkit wraps the placed object once (`wrapped` true, a
new id), so the warp lands on the corners. Gate as stage 4.

**Curved surfaces.** `fit_quad` is planar: box faces, bag fronts, totes, screens, posters. Cans,
bottles and mugs take the Cylinder or Arc Lower warp preset (Design Master [C3ZkcqB36xw 00:38];
Hastie [70L2ngS8raY 03:21]) or a hand mesh (Quick Fix Up [boONV-waIUk 01:05]), by hand. A later
`fit_quad` resets that curve (`reset` true). Several faces take one placeholder each.

## Numbers

| Value                                                   | Relative to                     | Source                                          |
| ------------------------------------------------------- | ------------------------------- | ----------------------------------------------- |
| `corner_error` under 1 px, `fit_check` under 0.5 px     | the requested quad              | toolkit, verified live                          |
| `drift` under 0.5 px                                    | corners before Replace Contents | toolkit, verified live                          |
| Fill 60 while fitting, 100 after a replace              | the placeholder                 | toolkit default                                 |
| Shading 85%, Highlights 50%                             | the two product copies          | toolkit default                                 |
| Displace scale 8; map blur max(1, doc width / 1500)     | the toolkit's defaults          | toolkit default                                 |
| Displace 4, map blur 1 px                               | a fabric tote                   | Dinda [_VNqOhHJIm8 06:11]; [_VNqOhHJIm8 05:39]  |
| Displace 15, map blur 3 px                              | a crushed can                   | Geller [0l2Ma_2B-A8 05:24]; [0l2Ma_2B-A8 01:04] |
| Displace 10, then 20; map blur 18 px for big folds only | a t-shirt                       | Dinda [sy1w5mTif-E 06:27]; [sy1w5mTif-E 05:54]  |
| Ink blur 1 px; 0.6 px with a stroke                     | the design                      | Dinda [_VNqOhHJIm8 07:17]; [_VNqOhHJIm8 08:55]  |
| Design opacity 90%                                      | a dark garment                  | Anders [rrxTM5AZALU 06:38]                      |

Toolkit thresholds are authoring-time, from one striped fixture: check them on your own images.
Expert values depend on pixel width, crease depth and material.

## Quality gates

- **Code:** after every fit, `corner_error` under 1 and `fit_check` under 0.5; `corners` returns
  `consistent` true. After every replace, `drift` under 0.5 and `content_size` unchanged. One new
  History state per call. `lighting` returns two layers; `displace` returns a `map` that exists;
  `batch` returns one `out` per design and leaves History as it found it. `A.deliverable(profile)`
  returns `[]`.
- **Visual:** each corner at 100%; the ramp under light and creases; the printable edge (no design
  on a lid, seam or hand); each export on the sheet. Rubric: [critique](references/critique.md).

## Common mistakes

| Mistake                                  | Looks like                                       | Fix                                               |
| ---------------------------------------- | ------------------------------------------------ | ------------------------------------------------- |
| Design placed straight on the photo      | each new design needs a new warp                 | a placeholder, then `replace_design`              |
| The logo as the test design              | light and creases fail on the next design        | a ramp or check design first                      |
| Multiply only, on a dark product         | the design sinks into the shadows                | `lighting`: Multiply below the mean, Screen above |
| Blend If read from the design layer      | highlights follow the artwork, not the product   | product copies (Dinda [sy1w5mTif-E 09:11])        |
| One mask per layer                       | fringes at the edges, masks out of step          | one group mask                                    |
| Displace map deleted or moved            | Replace Contents: "the file was not found"       | keep the map folder; re-run `displace`            |
| A fit judged by eye                      | corners a few px off, or a warp that did nothing | `corner_error`, `fit_check`, corner crops         |
| Foreshortened `size`                     | artwork squashed after a replace                 | the printed area's real ratio                     |
| A raster logo enlarged                   | soft edges, wrong letters                        | the SVG master, rendered at content size          |
| `fit_quad` after a hand curve            | the curve is gone                                | re-curve by hand after the fit                    |
| Plates from different sources in one set | the same design at different scales              | one plate set (Stanik [QTS-IWB3MKY 13:35])        |

## Handoffs

- **Receives** from scenario-photoshop-expert: routing and document state; from
  scenario-photoshop-compositing: a product placed in a scene that now needs its design; from
  scenario-photoshop-key-art: art to show on a product, a poster or a screen.
- **Delivers** a "Mockup: <name>" group (placeholder, Shading and Highlights copies, a Displace
  Smart Filter whose map stays on disk), one PNG per design, the gate numbers and the map path.
  Sizes and type for posters and thumbnails go to scenario-photoshop-key-art; a small plate to
  scenario-photoshop-upscale-restore; plate cleanup to scenario-photoshop-generative-edit; a product
  into a new scene to scenario-photoshop-compositing; the final audit to scenario-photoshop-expert.
- **Scenario siblings:** `scenario` (connection, `recommend`, price quote, Scenario job waiting),
  `scenario-product-shots` (plates, packshots, restaging), `scenario-image-editing` (background
  removal, vectorize, upscale), `scenario-brand-kit` (vector marks, logo variants).

## Photoshop 2026 notes

Measured on 27.11:

- A custom warp without `freeTransformCenterState` changes nothing, silently. It also needs the
  current box as `bounds`, 16 mesh points, and the box already on the quad's bounds.
- A smart object placed from a file warps about 10 px off at the top-left; `fit_quad` wraps it once
  with `newPlacedLayer`. A re-fit starts with `warpNone`.
- After a good fit, `nonAffineTransform` equals the quad's bounding box: that is `fit_check`.
- Replace Contents keeps the transform (300x200 after a 50% scale shows at 150x100) and renames the
  layer after the file; `replace_design` handles both.
- Deleting the active History snapshot sends the document to its opening state.
- A layer inserted inside a clipping chain releases the whole chain; `lighting` adds above its top.
- Blend If sets but never reads back: verify it on pixels.

Photoshop's 3D features were removed in 2024, so 3D mockup steps in older videos do not apply.

## References

- [`references/expert-notes.md`](references/expert-notes.md): the measured toolkit behavior, each
  expert's method, disagreements and deciders. Load when a case is not covered above.
- [`references/procedures.md`](references/procedures.md): code per stage. Load before writing an
  ExtendScript job.
- [`references/critique.md`](references/critique.md): the rubric. Load at stages 4 to 8.
- [`references/gui-paths.md`](references/gui-paths.md): curved warps, Blend If, ink blur, logo
  cutouts and templates by menu, for the user or a computer-use agent.
- [`references/sources.md`](references/sources.md): videos, credentials, URLs, docs.
- [`scripts/ps_mockup.py`](scripts/ps_mockup.py): the toolkit (docstring lists every call), on top
  of the lead's scripts.
