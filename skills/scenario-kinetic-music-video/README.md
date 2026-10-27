# scenario-kinetic-music-video (maintainer notes, not packaged)

## Origin

Sara Nemati own `kinetic-music-video` skill, built from the production of the Every Scenario music
video (and the kinetic music video it grew out of) and rewritten to be generic: any subject or none,
any looks, no project examples. Brought into this repository from the ZIP she exported on
2026-10-02.

## Edits for this repository

- Frontmatter reduced to `name`, `description` ("Use when", under 500 characters) and `license`; the
  name carries the `scenario-` prefix.
- Generative model names and ids removed (availability differs per team): lanes are named by
  capability and found with `recommend`. Parameter names are the ones that held at authoring time,
  with the schema as the authority.
- Credit amounts stated as relative costs, with `dry_run` before paid steps.
- En and em dashes replaced, scripts print usage when called without arguments, and the
  output-writing scripts refuse to replace an existing file without `--force`.
- Sibling references and the install invitation added; connection setup points to `scenario`.

## Portrait canvas

Added after import so the skill can serve vertical feeds. One canvas per project (`CANVAS` in the
timeline), with `--canvas` for a second ratio. `assets/engine/canvas.js` holds the presets, the 9:16
safe band (derived from the band `scenario-formats` and `scenario-video-ads` compose to, reading
their 6 to 13% per side as 6% left and 13% right, where the action rail sits), the per-canvas
timeline filter and `plateFit`. The HUD, the house subtitle and the scene template lay out inside
`E.SAFE`; every portrait-only behavior is gated off landscape.

Verified headless (Playwright's Chromium, software WebGL) with synthetic audio, lyrics and a
synthetic footage clip (frames, matte, tracking): landscape stills of both template branches
(footage and 3D) and the HUD, including a 150-character lyric line, are pixel-identical to the
pre-change engine at scales 1 and 0.5. Portrait and square stills were checked by eye with the safe
band outlined, and the error paths (bad canvas, bad timeline tag, an `--only` with nothing to
render) fail fast. `canvas.js` has a unit suite. Two plan-only application tests (portrait only;
both ratios) passed with notes.

A live application test then produced a full 1080p60 portrait video end to end (a 2:14 song, 24
style frames, 27 clips, 9 section agents, about 15k CU) and passed with notes. It found the portrait
subtitle running into the HUD counters, a `crop` that stretched plates, a `--chant` window with no
end, transcription passes overwriting each other, `still.mjs` keeping a stale sheet, and the doc
gaps behind a mic-covered lip-sync retake, the 720p-only cost anchors and a rejected reference crop.
All are fixed; `motion_library.md` §10 notes one production behind its portrait rules.

## 4K master

`--scale 2` reuses the canvas: layouts already scale with `E.SCALE`. Three things did not, and each
fix applies above scale 1 only, so the shader text and the encoder arguments at scale 1 or below are
unchanged.

- **Bloom:** UnrealBloomPass blurs in texels of its own targets, so at 4K the glow reached half as
  far. It now runs at the scale-1 size. Its bright pass then read only the middle of each 4×4 block,
  so it averages the block with four bilinear taps instead: without them, thin lines pulse as they
  move.
- **Grain and scanlines** keep 1080p cells (string substitution in the final shader).
- **Encoder:** above 1080p, `-level` from H.264 Table A-1 and `-threads 4`; `render.mjs` caps the
  workers to memory and refuses a 4K master past Level 5.2.

Evidence (an M-series Mac, ANGLE Metal, three 0.186.1, ffmpeg 7.1.1, a synthetic project with a
footage plate, matte and tracking, 2D and 3D type, grain, scanlines and the HUD):

- **Unchanged at scale 1 or below:** stills of every frame at scales 0.5 and 1, plus square and
  portrait, are pixel-identical to the previous engine. Four `render.mjs` files (960×540 at 30 fps
  on 2 workers, 1920×1080 at 60, 540×540 at 30, 1080×1920 at 60) are byte-identical.
  - Chrome's GPU canvas rasterizes large or scaled glyph edges with ±1 differences from run to run,
    in the old engine as in the new. The comparison runs with `--disable-accelerated-2d-canvas` (3
    of 3 repeat runs identical), so a difference can only come from the engine.
- **Moving thin lines** (0.5 to 1.5 px wide, half a 1080p pixel per frame), per-frame halo energy
  against 1080p: within 0.6% with the fix, up to 148% off with the bloom resized alone, 129% off
  with no fix. Area-downscaled PSNR against 1080p: 39.3, 27.9 and 24.2 dB.
- **Grain:** 4K grain is constant over 2×2 cells and correlates 0.79 with the 1080p pattern (−0.04
  before), the rest being 8-bit rounding near black.
- **Levels:** `h264Level` matched x264 medium's own pick in 30 cases from 176×144 to 5120×2880, so
  the pin changes no bytes at 4K60; a vitest case reruns that on CI's ffmpeg. With `-preset slow`,
  x264 signals 5.0 at 1080p60 on its own; `-level 4.2` makes it drop to 4 reference frames.
- **Cost:** a 4K frame took 3.3 times as long. Peak footprint per worker (Chrome, its GPU process
  and x264) was 2.5 GB at 1080p and 5.3 GB at 4K; `workerGB` adds about a gigabyte for real footage
  caches.

## What the record does not cover

- The skill is the creator's own document, not distilled here, so it does not follow the house
  layout for recipe skills: its `references/lessons.md` plays the Common mistakes role.
- Costs are the production's observed relative prices, not live quotes.
- The engine and scripts need Node with Playwright, ffmpeg and a Python environment
  (`scripts/scaffold.sh` builds it); the matte tool needs macOS (Apple Vision).
- Tests cover the dependency-light scripts, `canvas.js`, `render_lib.mjs` and `delivery_check.py`;
  the rest need the full environment and generated footage.
- The 4K path was checked on synthetic projects only, not yet in a live application test.
