"""
ps_audit: read the live Photoshop document as data, and grade it against a delivery profile.
Every scenario-photoshop-* skill gates its stages on these numbers before looking at a preview.

Library (each call is one ps_run job, read only, no history state):
  import ps_audit as A
  A.doc_state()                    # active document: size, ppi, mode, bits, profile, layer tree,
                                   # selection bounds, active layer, saved state, path, and
                                   # history {index, name, count}: the active History state
                                   # (gate on index and name; a step back keeps the count)
  A.doc_state(max_layers=400)      # cap on layers walked (big documents)
  A.layer_find(name)               # [{id, name, path, kind, bounds, visible}] for an exact name
  A.histogram_clip()               # % of pixels at 0 and 255 per channel on the merged image
  A.deliverable(profile)           # [] = pass, else a list of problems for "web", "print",
                                   # "social", "game-texture", "psd-handoff"
Shell:
  python3 ps_audit.py state | find NAME | clip | deliverable PROFILE

Kinds reported for layers: pixel, adjustment, fill, smart_object, text, shape, group, video,
other (from the Action Manager layerKind; the DOM kind misreads shapes and throws on some
adjustment layers). Bounds are [left, top, right, bottom] in pixels.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps_run  # noqa: E402

KIND_JS = r"""
// Action Manager layerKind, not the DOM's LayerKind: the DOM reports shape layers as SOLIDFILL
// and throws "Internal error" on newer adjustment layers such as Clarity (27.11).
var KINDS = {1: "pixel", 2: "adjustment", 3: "text", 4: "shape", 5: "smart_object", 6: "video",
             7: "group", 9: "fill", 10: "fill", 11: "fill", 12: "pixel"};
function kindOf(l) {
  if (l.typename === "LayerSet") return "group";
  try {
    var r = new ActionReference(); r.putIdentifier(charIDToTypeID("Lyr "), l.id);
    var k = executeActionGet(r).getInteger(stringIDToTypeID("layerKind"));
    if (KINDS[k]) return KINDS[k];
  } catch (e) {}
  return "other";
}
"""

STATE_JS = KIND_JS + r"""
var MAXL = %MAX%;
var count = 0, truncated = false;
function walk(container, path) {
  var out = [];
  for (var i = 0; i < container.layers.length; i++) {
    if (count >= MAXL) { truncated = true; break; }
    var l = container.layers[i]; count++;
    var b = null;
    try { b = [l.bounds[0].as("px"), l.bounds[1].as("px"), l.bounds[2].as("px"),
               l.bounds[3].as("px")]; } catch (e) {}
    var item = {id: l.id, name: l.name, path: path + "/" + l.name, kind: kindOf(l),
                visible: l.visible, opacity: Math.round(l.opacity), blend: String(l.blendMode)
                  .replace("BlendMode.", "").toLowerCase(), bounds: b};
    try { item.locked = l.allLocked; } catch (e) {}
    try { if (l.isBackgroundLayer) item.background = true; } catch (e) {}
    try { if (l.grouped) item.clipped = true; } catch (e) {}
    if (l.typename === "LayerSet") item.children = walk(l, item.path);
    out.push(item);
  }
  return out;
}
if (app.documents.length === 0) return {open: false};
var d = app.activeDocument;
var sel = null;
try { var sb = d.selection.bounds; sel = [sb[0].as("px"), sb[1].as("px"), sb[2].as("px"),
                                          sb[3].as("px")]; } catch (e) { sel = null; }
var prof = null; try { prof = d.colorProfileName; } catch (e) { prof = "untagged"; }
var path = null; try { path = d.fullName.fsName; } catch (e) {}
var al = null; try { al = {id: d.activeLayer.id, name: d.activeLayer.name}; } catch (e) {}
// Steps backward leave redo states in the list, so the length is no gate: the active state is.
var hs = d.historyStates, hi = -1;
for (var q = hs.length - 1; q >= 0; q--) if (hs[q] == d.activeHistoryState) { hi = q; break; }
var hist = {index: hi, name: d.activeHistoryState.name, count: hs.length};
return {open: true, name: d.name, id: d.id, path: path, saved: d.saved, width: d.width.as("px"),
        height: d.height.as("px"), ppi: d.resolution, mode: String(d.mode).replace("DocumentMode.", "")
          .toLowerCase(), bits: ({"BitsPerChannelType.ONE": 1, "BitsPerChannelType.EIGHT": 8,
          "BitsPerChannelType.SIXTEEN": 16, "BitsPerChannelType.THIRTYTWO": 32})[String(d.bitsPerChannel)],
        profile: prof, layers: walk(d, ""), layer_count_walked: count, truncated: truncated,
        selection: sel, active_layer: al, history: hist, documents_open: app.documents.length};
"""

FIND_JS = KIND_JS + r"""
var target = %NAME%, hits = [];
function walk(c, path) {
  for (var i = 0; i < c.layers.length; i++) {
    var l = c.layers[i];
    if (l.name === target) {
      var b = null;
      try { b = [l.bounds[0].as("px"), l.bounds[1].as("px"), l.bounds[2].as("px"),
                 l.bounds[3].as("px")]; } catch (e) {}
      hits.push({id: l.id, name: l.name, path: path + "/" + l.name, kind: kindOf(l),
                 bounds: b, visible: l.visible});
    }
    if (l.typename === "LayerSet") walk(l, path + "/" + l.name);
  }
}
if (app.documents.length === 0) return [];
walk(app.activeDocument, "");
return hits;
"""

CLIP_JS = r"""
// Channel.histogram reads the active layer, so measure a flattened copy of the whole image.
if (app.documents.length === 0) throw new Error("no document open");
var src = app.activeDocument, out = {};
var d = psr_dup(src, "psr_clip", true);
app.activeDocument = d;
try {
  try { d.flatten(); } catch (e) {}
  if (String(d.mode) !== "DocumentMode.RGB") out.skipped = "mode " + d.mode;
  else {
    var names = ["red", "green", "blue"];
    for (var c = 0; c < 3; c++) {
      var h = d.channels[c].histogram, total = 0;
      for (var i = 0; i < 256; i++) total += h[i];
      out[names[c]] = {black_pct: Math.round(1000 * h[0] / total) / 10,
                       white_pct: Math.round(1000 * h[255] / total) / 10};
    }
  }
} finally { psr_close(d); app.activeDocument = src; }
return out;
"""

PROFILES = {
    # name: (color mode, bits, profile substring or None, max long edge, min long edge, ppi)
    "web": ("rgb", 8, "sRGB", 4096, 600, None),
    "social": ("rgb", 8, "sRGB", 4096, 1080, None),
    "print": (None, None, None, None, 2400, 300),
    "game-texture": ("rgb", 8, None, 8192, 256, None),
    "psd-handoff": (None, None, None, None, None, None),
}


def _run(js, **kw):
    res = ps_run.run(js, timeout=kw.pop("timeout", 120), **kw)
    if not res.get("ok"):
        raise RuntimeError(res.get("error"))
    return res["result"]


def doc_state(max_layers=400):
    return _run(STATE_JS.replace("%MAX%", str(int(max_layers))))


def layer_find(name):
    return _run(FIND_JS.replace("%NAME%", json.dumps(name)))


def histogram_clip():
    return _run(CLIP_JS)


def _flat(layers):
    for layer in layers or []:
        yield layer
        yield from _flat(layer.get("children"))


def deliverable(profile, state=None):
    """Problems for a delivery profile ([] = pass). Pure function over doc_state() output."""
    if profile not in PROFILES:
        return ["unknown profile %r (known: %s)" % (profile, ", ".join(PROFILES))]
    s = state if state is not None else doc_state()
    if not s.get("open"):
        return ["no document open"]
    mode, bits, prof, max_edge, min_edge, ppi = PROFILES[profile]
    probs = []
    long_edge = max(s["width"], s["height"])
    if mode and s["mode"] != mode:
        probs.append("mode is %s, expected %s" % (s["mode"], mode))
    if bits and s["bits"] != bits:
        probs.append("bit depth is %s, expected %s" % (s["bits"], bits))
    if prof and prof.lower() not in str(s.get("profile", "")).lower():
        probs.append("profile is %r, expected %s" % (s.get("profile"), prof))
    if max_edge and long_edge > max_edge:
        probs.append("long edge %d px exceeds %d" % (long_edge, max_edge))
    if min_edge and long_edge < min_edge:
        probs.append("long edge %d px below %d" % (long_edge, min_edge))
    if ppi and s["ppi"] < ppi:
        probs.append("resolution %s ppi below %s" % (s["ppi"], ppi))
    layers = list(_flat(s.get("layers")))
    if profile == "game-texture":
        w, h = s["width"], s["height"]
        if w & (w - 1) or h & (h - 1):
            probs.append("size %dx%d is not a power of two" % (w, h))
    if profile == "psd-handoff":
        unnamed = [ly["name"] for ly in layers if ly["name"].startswith(("Layer ", "Group "))]
        if unnamed:
            probs.append("%d default layer names (e.g. %r)" % (len(unnamed), unnamed[0]))
        hidden = [ly["name"] for ly in layers if not ly.get("visible")]
        if hidden:
            probs.append("%d hidden layers left in the file" % len(hidden))
        empty = [ly["name"] for ly in layers
                 if ly.get("bounds") == [0, 0, 0, 0] and ly["kind"] != "group"]
        if empty:
            probs.append("%d empty layers" % len(empty))
        outside = [ly["name"] for ly in layers if ly.get("bounds") and ly["kind"] != "group" and
                   (ly["bounds"][0] < 0 or ly["bounds"][1] < 0 or ly["bounds"][2] > s["width"] or
                    ly["bounds"][3] > s["height"])]
        if outside:
            probs.append("%d layers extend past the canvas (e.g. %r)" % (len(outside), outside[0]))
    return probs


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd = argv[0]
    if cmd == "state":
        out = doc_state()
    elif cmd == "find":
        out = layer_find(argv[1])
    elif cmd == "clip":
        out = histogram_clip()
    elif cmd == "deliverable":
        out = deliverable(argv[1])
    else:
        print(__doc__)
        return 2
    print(json.dumps(out, indent=1))
    return 0 if not (cmd == "deliverable" and out) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
