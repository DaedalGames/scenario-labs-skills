"""Offline tests for the Photoshop toolkits: the job guard, the JSX builder, delivery profiles,
the ExtendScript each toolkit sends, and their pure helpers.

None of these talk to Photoshop. Live behavior is recorded in the family README.
"""

import contextlib
import io
import os
import re
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAMILY = os.path.join(ROOT, "skills", "dcc", "photoshop")
SCRIPTS = os.path.join(FAMILY, "scenario-photoshop-expert", "scripts")
sys.path.insert(0, SCRIPTS)
for skill in ("compositing", "game-art", "generative-edit", "key-art", "mockups", "upscale-restore"):
    sys.path.insert(0, os.path.join(FAMILY, "scenario-photoshop-" + skill, "scripts"))

import ps_audit  # noqa: E402
import ps_composite  # noqa: E402
import ps_gameart  # noqa: E402
import ps_gates  # noqa: E402
import ps_generative  # noqa: E402
import ps_io  # noqa: E402
import ps_keyart  # noqa: E402
import ps_mockup  # noqa: E402
import ps_retouch  # noqa: E402
import ps_review  # noqa: E402
import ps_run  # noqa: E402
import ps_upscale  # noqa: E402

TOOLKITS = (ps_audit, ps_composite, ps_gameart, ps_gates, ps_generative, ps_io, ps_keyart, ps_mockup, ps_retouch,
            ps_review, ps_upscale)
# ES3 reserves the Java keywords too; ExtendScript rejects them as bare object keys
# ("Illegal use of reserved word 'native'", measured on 27.11).
# ExtendScript evaluates a ? b : c ? d : e as (a ? b : c) ? d : e (measured on 27.11: a left
# alignment came out right-aligned). Parenthesize or use if/else.
CHAINED_TERNARY = re.compile(r"\?[^;()\n]*:[^;()\n]*\?")
RESERVED_KEY = re.compile(
    r"[{,]\s*(abstract|boolean|byte|char|class|const|double|enum|export|extends|final|float|goto|"
    r"implements|import|int|interface|long|native|package|private|protected|public|short|static|"
    r"super|synchronized|throws|transient|volatile)\s*:")


class GuardTest(unittest.TestCase):
    def test_refuses_save_close_quit(self):
        for body in (
            "app.activeDocument.save();",
            "doc.saveAs(new File('/tmp/x.psd'));",
            "app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);",
            "d . close ( );",
            "app.quit();",
            "executeAction(charIDToTypeID('save'), d, DialogModes.NO);",
            'executeAction(stringIDToTypeID("close"), d, DialogModes.NO);',
        ):
            self.assertTrue(ps_run.lint(body), body)

    def test_allows_helpers_and_reads(self):
        for body in (
            "var d = psr_new_doc(10, 10); psr_close(d); return 1;",
            "psr_export(app.activeDocument, '/tmp/a.png', 'png');",
            "return app.activeDocument.layers.length;",
            "var closed = false; return closed;",
        ):
            self.assertEqual(ps_run.lint(body), [], body)

    def test_run_refuses_before_touching_photoshop(self):
        res = ps_run.run("app.activeDocument.save();", ps={"path": "/nonexistent", "name": "x",
                                                          "version": "0"})
        self.assertEqual(res["exit"], 2)
        self.assertIn("guard refused", res["error"])


class BuildTest(unittest.TestCase):
    def test_body_and_undo_name_are_embedded(self):
        js = ps_run.build("return 41 + 1;", undo='Scenario: "fill"')
        self.assertIn("return 41 + 1;", js)
        self.assertIn('"Scenario: \\"fill\\""', js)
        self.assertIn("suspendHistory", js)
        self.assertIn(ps_run.RESULT_TAG, js)

    def test_no_undo_is_null(self):
        self.assertIn("var undo = null;", ps_run.build("return 1;"))

    def test_failed_job_closes_its_temp_documents(self):
        js = ps_run.build("throw new Error('x');")
        self.assertIn("__psr_created", js.split("%BODY%")[0] if "%BODY%" in js else js)
        self.assertIn("DONOTSAVECHANGES", js)

    def test_prelude_avoids_unicode_class_escapes(self):
        # ExtendScript's regex engine rejects \u escapes in character classes (measured, 27.11).
        self.assertNotRegex(ps_run.PRELUDE, r"\[[^\]]*\\u[0-9a-fA-F]{4}")


def state(**kw):
    base = {"open": True, "width": 1920, "height": 1080, "ppi": 72, "mode": "rgb", "bits": 8,
            "profile": "sRGB IEC61966-2.1", "layers": []}
    base.update(kw)
    return base


class DeliverableTest(unittest.TestCase):
    def test_web_pass(self):
        self.assertEqual(ps_audit.deliverable("web", state()), [])

    def test_web_wrong_profile_and_bits(self):
        probs = ps_audit.deliverable("web", state(profile="Display P3", bits=16))
        self.assertTrue(any("profile" in p for p in probs))
        self.assertTrue(any("bit depth" in p for p in probs))

    def test_print_needs_ppi(self):
        self.assertTrue(ps_audit.deliverable("print", state(width=3000, height=2000, ppi=72)))
        self.assertEqual(ps_audit.deliverable("print", state(width=3000, height=2000, ppi=300)),
                         [])

    def test_game_texture_power_of_two(self):
        self.assertTrue(ps_audit.deliverable("game-texture", state(width=1000, height=1000)))
        self.assertEqual(ps_audit.deliverable("game-texture", state(width=1024, height=512)), [])

    def test_handoff_flags_names_hidden_empty_outside(self):
        layers = [
            {"name": "Layer 3", "kind": "pixel", "visible": True, "bounds": [0, 0, 10, 10]},
            {"name": "Hidden", "kind": "pixel", "visible": False, "bounds": [0, 0, 10, 10]},
            {"name": "Empty", "kind": "pixel", "visible": True, "bounds": [0, 0, 0, 0]},
            {"name": "Title", "kind": "text", "visible": True, "bounds": [100, 100, 2500, 300]},
            {"name": "Grp", "kind": "group", "visible": True, "bounds": [0, 0, 5, 5],
             "children": [{"name": "Group 2", "kind": "group", "visible": True, "bounds": None}]},
        ]
        probs = ps_audit.deliverable("psd-handoff", state(layers=layers))
        text = " | ".join(probs)
        self.assertIn("default layer names", text)
        self.assertIn("hidden", text)
        self.assertIn("empty", text)
        self.assertIn("past the canvas", text)

    def test_unknown_profile(self):
        self.assertIn("unknown profile", ps_audit.deliverable("nope", state())[0])


class ProvenanceTest(unittest.TestCase):
    def test_round_trip_escapes_markup(self):
        fields = {"assetId": "asset_x", "prompt": 'a "red" ball & <box>', "cuCharged": "31.5"}
        xmp = ps_io.provenance_xmp(fields)
        self.assertNotIn('"red"', xmp)
        self.assertNotIn("<box>", xmp)
        self.assertEqual(ps_io.parse_xmp(xmp), dict(fields, schema="1"))

    def test_snake_case_keys_join_the_plugin_schema(self):
        xmp = ps_io.provenance_xmp({"asset_id": "a", "job_id": "j", "model": "m", "date": "d",
                                    "negative_prompt": "n"})
        self.assertEqual(ps_io.parse_xmp(xmp), {"schema": "1", "assetId": "a", "jobId": "j",
                                                "modelId": "m", "createdAt": "d",
                                                "negativePrompt": "n"})

    def test_skips_unsafe_keys_and_none(self):
        xmp = ps_io.provenance_xmp({"ok": "1", "bad key": "2", "x=y": "3", "none": None})
        self.assertEqual(ps_io.parse_xmp(xmp), {"schema": "1", "ok": "1"})

    def test_place_rejects_unknown_fit(self):
        with self.assertRaises(ValueError):
            ps_io.place("/nonexistent.png", "x", fit="stretch")


def job_scripts():
    for mod in TOOLKITS:
        for name, value in vars(mod).items():
            if name.endswith("_JS") and isinstance(value, str):
                yield "%s.%s" % (mod.__name__, name), value


class ToolkitJsTest(unittest.TestCase):
    def test_every_job_passes_the_guard(self):
        found = 0
        for where, js in job_scripts():
            found += 1
            self.assertEqual(ps_run.lint(js), [], where)
        self.assertGreater(found, 30)

    def test_no_reserved_word_keys(self):
        for where, js in job_scripts():
            self.assertIsNone(RESERVED_KEY.search(js), where)

    def test_no_chained_ternary(self):
        for where, js in job_scripts():
            self.assertIsNone(CHAINED_TERNARY.search(js), where)

    def test_every_toolkit_prints_help(self):
        for mod in TOOLKITS:
            if hasattr(mod, "main"):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(mod.main(["--help"]), 0, mod.__name__)
                self.assertIn("Library", out.getvalue(), mod.__name__)


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, size = 8, b"", None
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            size = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    return size, zlib.decompress(idat)


class MockupHelpersTest(unittest.TestCase):
    def test_quad_size_averages_opposite_sides(self):
        self.assertEqual(ps_mockup.quad_size([[0, 0], [400, 0], [400, 300], [0, 300]]), (400, 300))
        self.assertEqual(ps_mockup.quad_size([[0, 0], [100, 0], [80, 50], [20, 50]]), (80, 54))

    def test_quad_needs_four_corners(self):
        with self.assertRaises(ValueError):
            ps_mockup.quad_size([[0, 0], [1, 0], [1, 1]])

    def test_solid_png_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = ps_mockup._solid_png(os.path.join(tmp, "p.png"), 7, 3, (214, 72, 72))
            size, raw = read_png(path)
        self.assertEqual(size, (7, 3))
        self.assertEqual(len(raw), 3 * (1 + 7 * 3))
        self.assertEqual(tuple(raw[1:4]), (214, 72, 72))


class UpscaleHelpersTest(unittest.TestCase):
    def test_match_scale_caps_the_long_side(self):
        self.assertEqual(ps_upscale._coarse(512, 512), [256, 256])
        self.assertEqual(ps_upscale._coarse(4000, 3000), [256, 192])
        self.assertEqual(ps_upscale._coarse(200, 100), [200, 100])

    def test_lock_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            ps_upscale.lock("x", mode="multiply")


class GenerativeHelpersTest(unittest.TestCase):
    def test_default_margin_is_half_the_long_side_at_least_64(self):
        self.assertEqual(ps_generative.default_margin([340, 240, 460, 360]), 64)
        self.assertEqual(ps_generative.default_margin([0, 0, 400, 100]), 200)

    def test_tiles_cover_with_overlap(self):
        tiles = ps_generative.tile_plan([0, 0, 3000, 1000], 1024, 64)
        self.assertEqual(tiles[0][:2], [0, 0])
        self.assertEqual(max(t[2] for t in tiles), 3000)
        self.assertEqual(max(t[3] for t in tiles), 1000)
        xs = sorted({t[0] for t in tiles})
        for a, b in zip(xs, xs[1:]):
            self.assertLessEqual(b - a, 1024 - 64)
        self.assertEqual(ps_generative.tile_plan([10, 20, 500, 400], 1024), [[10, 20, 500, 400]])

    def test_tile_must_exceed_overlap(self):
        with self.assertRaises(ValueError):
            ps_generative.tile_plan([0, 0, 100, 100], 64, 64)

    def test_rejects_unknown_polarity_before_photoshop(self):
        with self.assertRaises(ValueError):
            ps_generative.capture(tempfile.gettempdir(), polarity="red")

    def test_expand_needs_a_positive_side_before_photoshop(self):
        for sides in ({}, {"right": -10}):
            with self.assertRaises(ValueError):
                ps_generative.expand(tempfile.gettempdir(), **sides)


class KeyArtHelpersTest(unittest.TestCase):
    def test_cover_bounds_fills_the_canvas_and_keeps_aspect(self):
        l, t, r, b = ps_keyart.cover_bounds(512, 512, 1280, 720)
        self.assertEqual((l, r), (0, 1280))
        self.assertAlmostEqual(b - t, 1280)
        self.assertAlmostEqual(t, -280)

    def test_cover_bounds_focus_stays_inside_the_crop(self):
        top = ps_keyart.cover_bounds(512, 512, 1280, 720, focus=(0.5, 0.0))
        self.assertEqual(top[1], 0)
        bottom = ps_keyart.cover_bounds(512, 512, 1280, 720, focus=(0.5, 1.0))
        self.assertAlmostEqual(bottom[3], 720)

    def test_presets_are_well_formed(self):
        for name, p in ps_keyart.PRESETS.items():
            w, h = p["size"]
            for z in p.get("unsafe", []):
                self.assertTrue(0 <= z[0] < z[2] <= w and 0 <= z[1] < z[3] <= h, name)
            self.assertGreater(p["display"], 0, name)

    def test_rejects_bad_input_before_photoshop(self):
        with self.assertRaises(ValueError):
            ps_keyart.new_canvas("tiktok-banner")
        with self.assertRaises(ValueError):
            ps_keyart.type_layers([{"name": "a", "text": "b"}])
        with self.assertRaises(ValueError):
            ps_keyart.type_layers([{"name": "a", "text": "b", "box": [0, 0, 1, 1], "align": "justify"}])
        with self.assertRaises(ValueError):
            ps_keyart.export_under(os.path.join(tempfile.gettempdir(), "x.gif"), 1000, fmt="gif")

class GameArtHelpersTest(unittest.TestCase):
    def test_pow2(self):
        self.assertTrue(ps_gameart.pow2(1024))
        self.assertFalse(ps_gameart.pow2(1000))
        self.assertFalse(ps_gameart.pow2(0))
        self.assertEqual(ps_gameart.next_pow2(1000), 1024)
        self.assertEqual(ps_gameart.next_pow2(512), 512)

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            ps_gameart.pack_channels("x.png", "a", "b", "c", a="d", fmt="png")
        with self.assertRaises(ValueError):
            ps_gameart.export_texture("x.tga", bits=16, fmt="tga")
        with self.assertRaises(ValueError):
            ps_gameart.export_texture("x.png", resample="lanczos")
        with self.assertRaises(ValueError):
            ps_gameart.id_select("ID", [0, 300, 0])
        with self.assertRaises(ValueError):
            ps_gameart.nine_slice_check(0, 8, 8, 8)
        with self.assertRaises(ValueError):
            ps_gameart.pack_channels("x.tga", "a", 300, None)


if __name__ == "__main__":
    unittest.main()

