"""
ps_mockup: put a flat design (a Scenario result, a logo, a label) onto a product photo the way
mockup builders do it by hand: a placeholder smart object fitted to four corners, the design
swapped in at the placeholder's exact content size, lighting rebuilt from the product's own
pixels, creases through Displace, and a batch export per design. Every edit is one named History
state; every fit reports where the corners actually landed.

Library:
  import ps_mockup as M
  M.placeholder(quad, name="Place Design Here", size=None, fill=60, mask_selection=True)
      # quad = [[x,y] TL, TR, BR, BL] in document px. A solid smart object of `size` (default:
      # the quad's mean edge lengths) inside group "Mockup: <name>", warped onto the quad, Fill
      # lowered so the product shows through while fitting. With a selection active, the
      # selection becomes the GROUP mask (the printable area).
  M.fit_quad(layer, quad)        # perspective warp of a smart object onto four corners
  M.corners(layer)               # where the corners are now: [[x,y] TL, TR, BR, BL]
  M.replace_design(layer, path, fit="cover")
      # the file resized and cropped ("cover"), padded ("contain") or stretched ("exact") to the
      # smart object's content size, then swapped in: the warp is kept, Fill goes back to 100
  M.lighting(layer, product, shade=85, light=50)
      # two copies of the product pixels clipped above the design: Multiply keeps only what is
      # darker than the product's mean under the design, Screen only what is brighter
  M.displace(layer, product, scale=8, blur=None, map_dir=None)
      # displacement map from the product pixels under the design, applied as a Smart Filter.
      # The filter re-reads the map file on every re-render, so the map is kept: in
      # "<document> maps/" next to a saved document, else Documents/Scenario Photoshop/
      # displace maps/. Returns its path; never delete it while the filter exists.
  M.batch(layer, designs, out_dir, fit="cover")
      # one merged PNG per design file; the document ends as it started
Shell:
  python3 ps_mockup.py placeholder X,Y,X,Y,X,Y,X,Y [--name N] [--size W,H] [--fill 60]
      | fit LAYER X,Y,X,Y,X,Y,X,Y | corners LAYER | replace LAYER FILE [--fit cover]
      | light LAYER PRODUCT [--shade 85] [--light 50] | displace LAYER PRODUCT [--scale 8]
      | batch LAYER OUT_DIR FILE [FILE ...]

Sources: mockup videos summarized in the skill (placeholder smart object first, lighting from
the product's own pixels, group mask for the printable area, Displace as a Smart Filter).
"""

import json
import math
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scenario-photoshop-expert", "scripts"))
import ps_gates as G  # noqa: E402
import ps_run  # noqa: E402

HELPERS_JS = r"""
var ARGS = %ARGS%;
function pm_c(s) { return charIDToTypeID(s); }
function pm_s(s) { return stringIDToTypeID(s); }
function pm_find(c, key) {
  for (var i = 0; i < c.layers.length; i++) {
    var l = c.layers[i];
    if ((typeof key === "number" && l.id === key) || (typeof key === "string" && l.name === key)) return l;
    if (l.typename === "LayerSet") { var r = pm_find(l, key); if (r) return r; }
  }
  return null;
}
function pm_layer(key) {
  var l = pm_find(app.activeDocument, key);
  if (!l) throw new Error("layer not found: " + key);
  if (l.typename === "LayerSet") throw new Error("needs a layer, not a group: " + key);
  app.activeDocument.activeLayer = l;
  return l;
}
function pm_so(key) {
  var l = pm_layer(key);
  if (String(l.kind) !== "LayerKind.SMARTOBJECT") throw new Error("not a smart object: " + key);
  return l;
}
function pm_more(l) {
  var r = new ActionReference(); r.putIdentifier(pm_c("Lyr "), l.id);
  return executeActionGet(r).getObjectValue(pm_s("smartObjectMore"));
}
function pm_size(l) {
  var s = pm_more(l).getObjectValue(pm_s("size"));
  return [s.getDouble(pm_s("width")), s.getDouble(pm_s("height"))];
}
// Box of the smart object's current transform. layer.bounds would give the opaque pixels only.
function pm_box(l) {
  var t = pm_more(l).getList(pm_s("transform")), xs = [], ys = [];
  for (var i = 0; i < 8; i += 2) { xs.push(t.getDouble(i)); ys.push(t.getDouble(i + 1)); }
  return [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)];
}
function pm_warp_style(m) {
  try { return typeIDToStringID(m.getObjectValue(pm_s("warp")).getEnumerationValue(pm_s("warpStyle"))); }
  catch (e) { return "warpNone"; }
}
function pm_mesh(m) {
  var w = m.getObjectValue(pm_s("warp")), pts = w.getObjectValue(pm_s("customEnvelopeWarp")).getList(pm_s("meshPoints")), o = [];
  for (var i = 0; i < pts.count; i++) {
    var p = pts.getObjectValue(i);
    o.push([p.getUnitDoubleValue(pm_s("horizontal")), p.getUnitDoubleValue(pm_s("vertical"))]);
  }
  return o;
}
function pm_warp_bounds(m) {
  try {
    var b = m.getObjectValue(pm_s("warp")).getObjectValue(pm_s("bounds"));
    return [b.getDouble(pm_s("left")), b.getDouble(pm_s("top")), b.getDouble(pm_s("right")), b.getDouble(pm_s("bottom"))];
  } catch (e) { return null; }
}
// A smart object placed from a file keeps its warp in content pixels (bounds 0,0,w,h); one
// converted from a layer keeps it in document pixels. On the first kind, a custom warp sent by
// script renders with one corner displaced (measured on 27.11), so it gets wrapped first.
function pm_placed_frame(l) {
  var m = pm_more(l), b = pm_warp_bounds(m), s = pm_size(l), box = pm_box(l);
  if (!b || b[0] !== 0 || b[1] !== 0 || Math.abs(b[2] - s[0]) > 0.01 || Math.abs(b[3] - s[1]) > 0.01) return false;
  return Math.abs(box[0]) > 0.01 || Math.abs(box[1]) > 0.01 || Math.abs(box[2] - s[0]) > 0.01 || Math.abs(box[3] - s[1]) > 0.01;
}
function pm_qbox(q) {
  var xs = [], ys = [];
  for (var i = 0; i < 4; i++) { xs.push(q[i][0]); ys.push(q[i][1]); }
  return [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)];
}
function pm_target(l) {
  app.activeDocument.activeLayer = l;
  var r = new ActionReference(); r.putEnumerated(pm_s("layer"), pm_s("ordinal"), pm_s("targetEnum"));
  var t = new ActionDescriptor(); t.putReference(pm_s("null"), r);
  // Without freeTransformCenterState the transform event records nothing and changes nothing.
  t.putEnumerated(pm_s("freeTransformCenterState"), pm_s("quadCenterState"), pm_s("QCSAverage"));
  return t;
}
function pm_unwarp(l) {
  var w = new ActionDescriptor(), t = pm_target(l);
  w.putEnumerated(pm_s("warpStyle"), pm_s("warpStyle"), pm_s("warpNone"));
  t.putObject(pm_s("warp"), pm_s("warp"), w);
  executeAction(pm_s("transform"), t, DialogModes.NO);
}
function pm_wrap(l) {
  var name = l.name;
  app.activeDocument.activeLayer = l;
  executeAction(pm_s("newPlacedLayer"), undefined, DialogModes.NO);
  var w = app.activeDocument.activeLayer; w.name = name;
  return w;
}
function pm_align(l, b) {
  var c = pm_box(l);
  l.resize((b[2] - b[0]) / (c[2] - c[0]) * 100, (b[3] - b[1]) / (c[3] - c[1]) * 100, AnchorPosition.TOPLEFT);
  c = pm_box(l);
  l.translate(UnitValue(b[0] - c[0], "px"), UnitValue(b[1] - c[1], "px"));
}
// Homography from the unit square onto the quad, sampled at thirds: the 4x4 control net of a
// custom warp, in document pixels, read through `bounds` = the layer's current box.
function pm_warp(l, q) {
  var x0=q[0][0],y0=q[0][1],x1=q[1][0],y1=q[1][1],x2=q[2][0],y2=q[2][1],x3=q[3][0],y3=q[3][1];
  var dx1=x1-x2,dx2=x3-x2,dy1=y1-y2,dy2=y3-y2,sx=x0-x1+x2-x3,sy=y0-y1+y2-y3,den=dx1*dy2-dx2*dy1;
  if (Math.abs(den) < 1e-9) throw new Error("degenerate quad");
  var g=(sx*dy2-dx2*sy)/den, h=(dx1*sy-sx*dy1)/den;
  var mesh = new ActionList();
  for (var j = 0; j < 4; j++) for (var i = 0; i < 4; i++) {
    var u = i / 3, v = j / 3, z = 1 + g*u + h*v, pd = new ActionDescriptor();
    pd.putUnitDouble(pm_s("horizontal"), pm_s("pixelsUnit"), (x0 + (x1-x0+g*x1)*u + (x3-x0+h*x3)*v) / z);
    pd.putUnitDouble(pm_s("vertical"), pm_s("pixelsUnit"), (y0 + (y1-y0+g*y1)*u + (y3-y0+h*y3)*v) / z);
    mesh.putObject(pm_s("rationalPoint"), pd);
  }
  var b = pm_box(l), w = new ActionDescriptor(), bd = new ActionDescriptor(), t = pm_target(l);
  w.putEnumerated(pm_s("warpStyle"), pm_s("warpStyle"), pm_s("warpCustom"));
  bd.putDouble(pm_s("top"), b[1]); bd.putDouble(pm_s("left"), b[0]);
  bd.putDouble(pm_s("bottom"), b[3]); bd.putDouble(pm_s("right"), b[2]);
  w.putObject(pm_s("bounds"), pm_s("classFloatRect"), bd);
  var ce = new ActionDescriptor(); ce.putList(pm_s("meshPoints"), mesh);
  w.putObject(pm_s("customEnvelopeWarp"), pm_s("customEnvelopeWarp"), ce);
  t.putObject(pm_s("warp"), pm_s("warp"), w);
  executeAction(pm_s("transform"), t, DialogModes.NO);
}
// Fit a smart object onto the quad. Measured on 27.11, the only sequence that lands every corner:
// reset any warp (a new warp is read through the current box, so an old one skews it), wrap a
// placed-from-file object, scale and move the box onto the quad's bounding box (a box far from
// the quad renders garbage), then warp. Returns the layer (a new id after a wrap) and
// `check`: the largest gap between nonAffineTransform and the quad's bounding box, which is
// near 0 after a good fit and several px when a corner is displaced.
function pm_fit(l, q) {
  var out = {reset: false, wrapped: false};
  if (pm_warp_style(pm_more(l)) !== "warpNone") { pm_unwarp(l); out.reset = true; }
  if (pm_placed_frame(l)) { l = pm_wrap(l); out.wrapped = true; }
  var qb = pm_qbox(q);
  pm_align(l, qb);
  pm_warp(l, q);
  var na = pm_more(l).getList(pm_s("nonAffineTransform")), bc = [qb[0], qb[1], qb[2], qb[1], qb[2], qb[3], qb[0], qb[3]], e = 0;
  for (var i = 0; i < 8; i++) e = Math.max(e, Math.abs(na.getDouble(i) - bc[i]));
  out.layer = l;
  out.check = Math.round(e * 100) / 100;
  return out;
}
// Corners TL, TR, BR, BL in document pixels. The stored mesh sits in the frame of the box the
// object had when it was converted, so its corners are mapped from their own bounding box onto
// the current box. `consistent` is false when that mapping does not hold: a hand-made warp whose
// edges bulge past the corners, or a content-pixel warp on a placed object.
function pm_corners(l) {
  var m = pm_more(l);
  if (pm_warp_style(m) !== "warpCustom") {
    var t = m.getList(pm_s("transform"));
    return {corners: [[t.getDouble(0), t.getDouble(1)], [t.getDouble(2), t.getDouble(3)],
                      [t.getDouble(4), t.getDouble(5)], [t.getDouble(6), t.getDouble(7)]], consistent: true};
  }
  var mesh = pm_mesh(m), n = mesh.length, side = Math.round(Math.sqrt(n)), idx = [0, side - 1, n - 1, n - side], c = [];
  for (var i = 0; i < 4; i++) c.push(mesh[idx[i]]);
  var cb = pm_qbox(c), ab = pm_qbox([mesh[0], mesh[0], mesh[0], mesh[0]]), box = pm_box(l), e = 0;
  for (var j = 0; j < n; j++) ab = [Math.min(ab[0], mesh[j][0]), Math.min(ab[1], mesh[j][1]), Math.max(ab[2], mesh[j][0]), Math.max(ab[3], mesh[j][1])];
  for (var k = 0; k < 4; k++) e = Math.max(e, Math.abs(ab[k] - cb[k]));
  var sx = (box[2] - box[0]) / (cb[2] - cb[0]), sy = (box[3] - box[1]) / (cb[3] - cb[1]), out = [];
  for (var q = 0; q < 4; q++) out.push([box[0] + (c[q][0] - cb[0]) * sx, box[1] + (c[q][1] - cb[1]) * sy]);
  return {corners: out, consistent: e < 1 && !pm_placed_frame(l)};
}
function pm_err(a, q) {
  var e = 0;
  for (var i = 0; i < 4; i++) e = Math.max(e, Math.sqrt(Math.pow(a[i][0] - q[i][0], 2) + Math.pow(a[i][1] - q[i][1], 2)));
  return Math.round(e * 100) / 100;
}
function pm_round(c) {
  var o = []; for (var i = 0; i < c.length; i++) o.push([Math.round(c[i][0] * 10) / 10, Math.round(c[i][1] * 10) / 10]);
  return o;
}
function pm_chain_top(l) {
  var p = l.parent, idx = -1;
  for (var i = 0; i < p.layers.length; i++) if (p.layers[i].id === l.id) { idx = i; break; }
  var top = l;
  for (var j = idx - 1; j >= 0; j--) {
    var x = p.layers[j], g = false;
    try { g = x.grouped; } catch (e) {}
    if (!g) break;
    top = x;
  }
  return top;
}
function pm_place(path) {
  var pd = new ActionDescriptor(); pd.putPath(pm_c("null"), new File(path));
  pd.putEnumerated(pm_c("FTcs"), pm_c("QCSt"), pm_c("Qcsa"));
  executeAction(pm_c("Plc "), pd, DialogModes.NO);
  return app.activeDocument.activeLayer;
}
function pm_replace(path) {
  var rd = new ActionDescriptor(); rd.putPath(pm_c("null"), new File(path));
  executeAction(pm_s("placedLayerReplaceContents"), rd, DialogModes.NO);
}
function pm_mask_from_selection() {
  var desc = new ActionDescriptor(); desc.putClass(pm_c("Nw  "), pm_c("Chnl"));
  var ref = new ActionReference(); ref.putEnumerated(pm_c("Chnl"), pm_c("Chnl"), pm_c("Msk "));
  desc.putReference(pm_c("At  "), ref);
  desc.putEnumerated(pm_c("Usng"), pm_c("UsrM"), pm_c("RvlS"));
  executeAction(pm_c("Mk  "), desc, DialogModes.NO);
}
function pm_has_selection(d) { try { d.selection.bounds; return true; } catch (e) { return false; } }
if (app.documents.length === 0) throw new Error("no document open");
var d = app.activeDocument;
"""

PLACEHOLDER_JS = r"""
var ch = null;
if (ARGS.mask_selection && pm_has_selection(d)) { ch = d.channels.add(); ch.name = "pm_sel"; d.selection.store(ch); d.selection.deselect(); }
var top = d.layers[0];
var grp = d.layerSets.add();
grp.name = "Mockup: " + ARGS.name;
grp.move(top, ElementPlacement.PLACEBEFORE);
d.activeLayer = grp;
var L = pm_place(ARGS.path);
L.move(grp, ElementPlacement.INSIDE);
L.name = ARGS.name;
var fit = pm_fit(L, ARGS.quad);
L = fit.layer;
L.fillOpacity = ARGS.fill;
if (ch) {
  d.activeLayer = grp; d.selection.load(ch); pm_mask_from_selection(); d.selection.deselect();
  ch.remove(); d.activeChannels = d.componentChannels;
}
var c = pm_corners(L).corners;
return {id: L.id, name: L.name, group: grp.name, size: pm_size(L), corners: pm_round(c),
        corner_error: pm_err(c, ARGS.quad), fit_check: fit.check, group_mask: !!ch};
"""

FIT_JS = r"""
var fit = pm_fit(pm_so(ARGS.layer), ARGS.quad), L = fit.layer, c = pm_corners(L).corners;
return {id: L.id, corners: pm_round(c), corner_error: pm_err(c, ARGS.quad), fit_check: fit.check,
        reset: fit.reset, wrapped: fit.wrapped};
"""

CORNERS_JS = r"""
var L = pm_so(ARGS.layer), c = pm_corners(L);
return {id: L.id, corners: pm_round(c.corners), consistent: c.consistent, size: pm_size(L), fill: L.fillOpacity};
"""

REPLACE_JS = r"""
var L = pm_so(ARGS.layer);
var sz = pm_size(L), before = pm_corners(L).corners;
var src = app.open(new File(ARGS.path));
__psr_created.push(src.id);
if (src.layers.length > 1) src.mergeVisibleLayers();
if (src.activeLayer.isBackgroundLayer) src.activeLayer.isBackgroundLayer = false;
var W = src.width.as("px"), H = src.height.as("px"), sx = sz[0] / W, sy = sz[1] / H;
if (ARGS.fit === "cover") sx = sy = Math.max(sx, sy);
else if (ARGS.fit === "contain") sx = sy = Math.min(sx, sy);
var rw = Math.max(1, Math.round(W * sx)), rh = Math.max(1, Math.round(H * sy));
if (rw !== W || rh !== H)
  src.resizeImage(UnitValue(rw, "px"), UnitValue(rh, "px"), null, ResampleMethod.BICUBICAUTOMATIC);
if (rw !== sz[0] || rh !== sz[1])
  src.resizeCanvas(UnitValue(sz[0], "px"), UnitValue(sz[1], "px"), AnchorPosition.MIDDLECENTER);
psr_export(src, ARGS.tmp, "png");
psr_close(src);
app.activeDocument = d;
d.activeLayer = L;
var keep = L.name;
pm_replace(ARGS.tmp);
L = d.activeLayer;
// Replace Contents renames the layer after the file; scripts find layers by name.
L.name = keep;
if (ARGS.reset_fill) L.fillOpacity = 100;
var after = pm_corners(L).corners;
return {id: L.id, content_size: sz, source_size: [W, H], scale: [Math.round(sx * 1000) / 1000, Math.round(sy * 1000) / 1000],
        corners: pm_round(after), drift: pm_err(after, before), fill: L.fillOpacity};
"""

LIGHT_JS = r"""
var L = pm_so(ARGS.layer), P = pm_layer(ARGS.product), top = pm_chain_top(L), made = [];
function copy(name, mode, lo, hi, opacity) {
  d.activeLayer = P;
  var c = P.duplicate(top, ElementPlacement.PLACEBEFORE);
  d.activeLayer = c;
  if (String(c.kind) !== "LayerKind.NORMAL") c.rasterize(RasterizeType.ENTIRELAYER);
  c.name = name;
  c.desaturate();
  c.adjustLevels(lo, hi, 1.0, 0, 255);
  c.blendMode = mode;
  c.opacity = opacity;
  c.grouped = true;
  top = c;
  made.push({id: c.id, name: c.name});
}
var m = Math.max(2, Math.min(253, Math.round(ARGS.neutral)));
if (ARGS.shade > 0) copy(ARGS.prefix + "Shading (product)", BlendMode.MULTIPLY, 0, m, ARGS.shade);
if (ARGS.light > 0) copy(ARGS.prefix + "Highlights (product)", BlendMode.SCREEN, m, 255, ARGS.light);
return {neutral: m, layers: made};
"""

DISPLACE_JS = r"""
var L = pm_so(ARGS.layer), P = pm_layer(ARGS.product);
// The Smart Filter keeps only the map's path and re-reads it on every re-render (a later content
// replace fails with "file was not found" once it is gone), so the map is kept on disk.
var dir = ARGS.map_dir ? new Folder(ARGS.map_dir) : null;
if (!dir) {
  try { dir = new Folder(d.path.fsName + "/" + d.name.replace(/\.[^.]+$/, "") + " maps"); }
  catch (e) { dir = new Folder(Folder.myDocuments.fsName + "/Scenario Photoshop/displace maps"); }
}
if (!dir.exists && !dir.create()) throw new Error("cannot create " + dir.fsName);
var stem = (d.name.replace(/\.[^.]+$/, "") + " " + L.name).replace(/[\\\/:*?"<>|]/g, "_");
var map = new File(dir.fsName + "/" + stem + " displace.psd");
for (var n = 2; map.exists; n++) map = new File(dir.fsName + "/" + stem + " displace " + n + ".psd");
var b = [Math.max(0, L.bounds[0].as("px")), Math.max(0, L.bounds[1].as("px")),
         Math.min(d.width.as("px"), L.bounds[2].as("px")), Math.min(d.height.as("px"), L.bounds[3].as("px"))];
var t = psr_dup(d, "displace map", false);
app.activeDocument = t;
function keep(c) {
  var hit = false;
  for (var i = 0; i < c.layers.length; i++) {
    var x = c.layers[i];
    if (x.id === P.id) { x.visible = true; hit = true; }
    else if (x.typename === "LayerSet" && keep(x)) { x.visible = true; hit = true; }
    else x.visible = false;
  }
  return hit;
}
if (!keep(t)) throw new Error("product layer not found in the copy");
t.flatten();
t.crop([UnitValue(b[0], "px"), UnitValue(b[1], "px"), UnitValue(b[2], "px"), UnitValue(b[3], "px")]);
t.activeLayer.desaturate();
var r = ARGS.blur;
if (r === null) r = Math.max(1, Math.round(d.width.as("px") / 1500 * 10) / 10);
if (r > 0) t.activeLayer.applyGaussianBlur(r);
psr_export(t, map.fsName, "psd");
psr_close(t);
app.activeDocument = d;
d.activeLayer = L;
var dd = new ActionDescriptor();
dd.putInteger(pm_c("HrzS"), ARGS.scale);
dd.putInteger(pm_c("VrtS"), ARGS.scale);
dd.putEnumerated(pm_c("DspM"), pm_c("DspM"), pm_c("StrF"));
dd.putEnumerated(pm_c("UndA"), pm_c("UndA"), pm_c("RptE"));
dd.putPath(pm_c("DspF"), map);
executeAction(pm_c("Dspl"), dd, DialogModes.NO);
return {id: L.id, map: map.fsName, map_box: b, blur: r, scale: ARGS.scale};
"""

# One design = one replace state; the export works on a temporary copy and adds none. Stepping
# back one state therefore returns to the document as it was, even at the History limit. (Deleting
# an active snapshot instead sends History to the opening state: measured.)
EXPORT_JS = r"""
var c = psr_dup(d, d.name + " export", true);
var p = psr_export(c, ARGS.out, "png");
psr_close(c);
app.activeDocument = d;
if (d.historyStates[d.historyStates.length - 1].name !== ARGS.state) throw new Error("unexpected History state");
d.activeHistoryState = d.historyStates[d.historyStates.length - 2];
return p;
"""


def _run(js, args, undo=None, timeout=240):
    body = HELPERS_JS.replace("%ARGS%", json.dumps(args)) + js
    res = ps_run.run(body, undo=undo, timeout=timeout)
    if not res.get("ok"):
        raise RuntimeError("%s (line %s)" % (res.get("error"), res.get("line")))
    return res["result"]


def _key(v):
    return int(v) if isinstance(v, str) and v.isdigit() else v


def _check_quad(quad):
    if len(quad) != 4 or any(len(p) != 2 for p in quad):
        raise ValueError("quad needs four [x, y] corners: TL, TR, BR, BL")
    return [[float(x), float(y)] for x, y in quad]


def _solid_png(path, w, h, rgb):
    row = b"\x00" + bytes(rgb) * w
    raw = zlib.compress(row * h, 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    return path


def _tmp(suffix):
    fd, p = tempfile.mkstemp(prefix="scenario_mockup_", suffix=suffix)
    os.close(fd)
    return p


def quad_size(quad):
    q = _check_quad(quad)

    def dist(a, b):
        return math.hypot(b[0] - a[0], b[1] - a[1])

    return (max(1, round((dist(q[0], q[1]) + dist(q[3], q[2])) / 2)),
            max(1, round((dist(q[0], q[3]) + dist(q[1], q[2])) / 2)))


def placeholder(quad, name="Place Design Here", size=None, fill=60, color=(214, 72, 72),
                mask_selection=True, undo="Scenario: Mockup placeholder"):
    q = _check_quad(quad)
    w, h = size or quad_size(q)
    png = _solid_png(_tmp(".png"), int(w), int(h), color)
    try:
        return _run(PLACEHOLDER_JS, {"quad": q, "name": name, "path": png, "fill": fill,
                                     "mask_selection": bool(mask_selection)}, undo=undo)
    finally:
        os.remove(png)


def fit_quad(layer, quad, undo="Scenario: Fit to corners"):
    return _run(FIT_JS, {"layer": _key(layer), "quad": _check_quad(quad)}, undo=undo)


def corners(layer):
    return _run(CORNERS_JS, {"layer": _key(layer)})


def replace_design(layer, path, fit="cover", reset_fill=True, undo="Scenario: Replace design"):
    if fit not in ("cover", "contain", "exact"):
        raise ValueError("fit must be cover, contain or exact")
    tmp = _tmp(".png")
    try:
        return _run(REPLACE_JS, {"layer": _key(layer), "path": os.path.abspath(path), "fit": fit,
                                 "tmp": tmp, "reset_fill": bool(reset_fill)}, undo=undo)
    finally:
        os.remove(tmp)


def lighting(layer, product, shade=85, light=50, prefix="", undo="Scenario: Product lighting"):
    under = G.stats(layer=_key(product), region={"alpha": _key(layer)})
    out = _run(LIGHT_JS, {"layer": _key(layer), "product": _key(product), "shade": shade,
                          "light": light, "prefix": prefix, "neutral": under["luminance"]},
               undo=undo)
    out["product_under_design"] = under
    return out


def displace(layer, product, scale=8, blur=None, map_dir=None, undo="Scenario: Displace"):
    return _run(DISPLACE_JS, {"layer": _key(layer), "product": _key(product), "scale": int(scale),
                              "blur": blur, "map_dir": map_dir}, undo=undo)


def batch(layer, designs, out_dir, fit="cover"):
    os.makedirs(out_dir, exist_ok=True)
    state = "Scenario: Batch design"
    results = []
    for path in designs:
        r = replace_design(layer, path, fit=fit, undo=state)
        base = os.path.splitext(os.path.basename(path))[0]
        out = os.path.abspath(os.path.join(out_dir, base + " mockup.png"))
        r["out"] = _run(EXPORT_JS, {"out": out, "state": state})
        r["design"] = path
        results.append(r)
    return results


def _opt(argv, flag, cast=str, default=None):
    if flag in argv:
        i = argv.index(flag)
        return cast(argv[i + 1])
    return default


def _quad(s):
    v = [float(x) for x in s.split(",")]
    if len(v) != 8:
        raise ValueError("quad needs 8 numbers: TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy")
    return [v[0:2], v[2:4], v[4:6], v[6:8]]


def _pair(s):
    return tuple(int(x) for x in s.split(",")) if s else None


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    try:
        if cmd == "placeholder":
            out = placeholder(_quad(argv[1]), _opt(argv, "--name", str, "Place Design Here"),
                              _pair(_opt(argv, "--size")), _opt(argv, "--fill", float, 60))
        elif cmd == "fit":
            out = fit_quad(argv[1], _quad(argv[2]))
        elif cmd == "corners":
            out = corners(argv[1])
        elif cmd == "replace":
            out = replace_design(argv[1], argv[2], _opt(argv, "--fit", str, "cover"))
        elif cmd == "light":
            out = lighting(argv[1], argv[2], _opt(argv, "--shade", float, 85),
                           _opt(argv, "--light", float, 50))
        elif cmd == "displace":
            out = displace(argv[1], argv[2], _opt(argv, "--scale", int, 8))
        elif cmd == "batch":
            out = batch(argv[1], argv[3:], argv[2])
        else:
            print("unknown command: " + cmd, file=sys.stderr)
            return 2
    except (RuntimeError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(json.dumps({"ok": True, "result": out}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
