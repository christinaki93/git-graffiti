"""Cross-checks that editor.html agrees with gitgraffiti.py.

The editor duplicates the calendar maths and the font in JavaScript, so the
risk is drift: art placed in the browser landing on different dates than the
CLI computes. These tests execute the editor's own JavaScript and compare its
answers against the Python implementation.

Skipped if no JavaScript engine is available. macOS ships one as part of
JavaScriptCore, so this normally runs without installing anything.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import date

import gitgraffiti as gg
from font import GLYPHS

HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR = os.path.join(HERE, "editor.html")
JSC = ("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A"
       "/Helpers/jsc")


def find_js_engine():
    for name in ("node", "deno", "bun"):
        path = shutil.which(name)
        if path:
            return [path]
    if os.path.exists(JSC):
        return [JSC]
    return None


def editor_script():
    """The <script> body of editor.html."""
    with open(EDITOR) as handle:
        html = handle.read()
    start = html.index("<script>") + len("<script>")
    return html[start:html.index("</script>", start)]


def pure_js():
    """The parts of the editor that do not touch the DOM.

    Everything above the control wiring (the font, the constants, the date
    helpers) plus the two export functions.
    """
    script = editor_script()
    head = script[:script.index("// ---------- build controls")]
    export = script[script.index("// ---------- export ----------"):
                    script.index("function update()")]
    return head + export


def run_js(body):
    """Run `body` with a print shim and parse its JSON output."""
    engine = find_js_engine()
    prelude = ("var __out = (typeof console !== 'undefined' && console.log)\n"
               "  ? function (s) { console.log(s); }\n"
               "  : function (s) { print(s); };\n")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(prelude + pure_js() + "\n" + body)
        path = handle.name
    try:
        result = subprocess.run(engine + [path], capture_output=True, text=True)
        # jsc reports uncaught exceptions on stdout, node on stderr.
        if result.returncode != 0:
            raise AssertionError("javascript failed:\n%s\n%s"
                                 % (result.stdout.strip(), result.stderr.strip()))
        return json.loads(result.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(path)


class EditorStructureTests(unittest.TestCase):
    """Checks that do not need a JavaScript engine."""

    def test_every_referenced_id_exists(self):
        with open(EDITOR) as handle:
            html = handle.read()
        declared = set(re.findall(r'id="([^"]+)"', html))
        used = set(re.findall(r'getElementById\("([^"]+)"\)', html))
        self.assertEqual(used - declared, set(),
                         "editor.html references ids that do not exist")

    def test_page_is_self_contained(self):
        """No external fetches: the editor has to work from file://."""
        with open(EDITOR) as handle:
            html = handle.read()
        self.assertNotIn("<script src", html)
        self.assertNotIn("stylesheet", html)
        self.assertNotIn("http://", html)

    def test_cell_geometry_is_not_duplicated_in_js(self):
        """Month labels are positioned in px, read back from the CSS vars.

        A hardcoded pixel step silently desyncs the labels from the grid the
        moment --cell or --gap changes.
        """
        with open(EDITOR) as handle:
            html = handle.read()
        self.assertIn('css.getPropertyValue("--cell")', html)
        self.assertIn('css.getPropertyValue("--gap")', html)


@unittest.skipUnless(find_js_engine(), "no javascript engine available")
class EditorSyntaxTests(unittest.TestCase):
    def test_whole_script_parses(self):
        """Parse the entire script, DOM code included, without running it."""
        engine = find_js_engine()
        source = editor_script()
        with tempfile.NamedTemporaryFile("w", suffix=".js",
                                         delete=False) as handle:
            # Wrapping in an uncalled function parses without executing.
            handle.write("function __never() {\n" + source + "\n}\n")
            path = handle.name
        try:
            result = subprocess.run(engine + [path], capture_output=True,
                                    text=True)
            self.assertEqual(result.returncode, 0,
                             "editor.html script does not parse:\n%s\n%s"
                             % (result.stdout.strip(), result.stderr.strip()))
        finally:
            os.unlink(path)


@unittest.skipUnless(find_js_engine(), "no javascript engine available")
class EditorParityTests(unittest.TestCase):
    def test_font_matches_python(self):
        data = run_js("__out(JSON.stringify(FONT));")
        self.assertEqual(data, GLYPHS,
                         "editor.html font is stale; re-run embed_font.py")

    def test_rolling_canvas_matches_python(self):
        data = run_js("""
            var t = new Date(Date.UTC(2026, 7, 5));
            var cv = rollingCanvas(t);
            __out(JSON.stringify({
                start: iso(cv.start), cols: cv.cols,
                first: iso(cv.first), last: iso(cv.last)
            }));
        """)
        expected = gg.rolling_canvas(date(2026, 8, 5))
        self.assertEqual(data["start"], expected.start.isoformat())
        self.assertEqual(data["cols"], expected.cols)
        self.assertEqual(data["first"], expected.first.isoformat())
        self.assertEqual(data["last"], expected.last.isoformat())

    def test_year_canvases_match_python(self):
        data = run_js("""
            var t = new Date(Date.UTC(2026, 7, 5));
            var out = {};
            for (var y = 2015; y <= 2035; y++) {
                var cv = yearCanvas(y, t);
                out[y] = {start: iso(cv.start), cols: cv.cols,
                          first: iso(cv.first), last: iso(cv.last)};
            }
            __out(JSON.stringify(out));
        """)
        today = date(2026, 8, 5)
        for year in range(2015, 2036):
            expected = gg.calendar_year_canvas(year, today)
            got = data[str(year)]
            self.assertEqual(got["start"], expected.start.isoformat(), year)
            self.assertEqual(got["cols"], expected.cols, year)
            self.assertEqual(got["first"], expected.first.isoformat(), year)
            self.assertEqual(got["last"], expected.last.isoformat(), year)

    def test_cell_dates_match_python(self):
        data = run_js("""
            var t = new Date(Date.UTC(2026, 7, 5));
            var cv = yearCanvas(2025, t);
            var out = [];
            for (var c = 0; c < cv.cols; c++)
                for (var r = 0; r < 7; r++)
                    out.push(iso(cellDate(cv, c, r)));
            __out(JSON.stringify(out));
        """)
        canvas = gg.calendar_year_canvas(2025, date(2026, 8, 5))
        expected = [canvas.cell_date(c, r).isoformat()
                    for c in range(canvas.cols) for r in range(gg.ROWS)]
        self.assertEqual(data, expected)

    def test_exported_bitmap_round_trips_through_the_parser(self):
        """What the editor exports must parse back to the same levels."""
        data = run_js("""
            canvas = yearCanvas(2025, new Date(Date.UTC(2026, 7, 5)));
            cells = blankCells(canvas.cols);
            cells[0][10] = 1; cells[3][11] = 2;
            cells[6][12] = 3; cells[2][14] = 4;
            __out(JSON.stringify({bitmap: toBitmap(), min: bounds().min}));
        """)
        pattern = gg.parse_bitmap(data["bitmap"])
        offset = data["min"]
        self.assertEqual(pattern[0][10 - offset], 1)
        self.assertEqual(pattern[3][11 - offset], 2)
        self.assertEqual(pattern[6][12 - offset], 3)
        self.assertEqual(pattern[2][14 - offset], 4)

    def test_offset_in_the_generated_command_restores_position(self):
        """Exported bitmap + reported offset must reproduce the exact dates."""
        data = run_js("""
            var cv = yearCanvas(2025, new Date(Date.UTC(2026, 7, 5)));
            canvas = cv;
            cells = blankCells(cv.cols);
            var painted = [[1, 20], [4, 21], [2, 25]];
            for (var i = 0; i < painted.length; i++)
                cells[painted[i][0]][painted[i][1]] = 4;
            var dates = painted.map(function (p) {
                return iso(cellDate(cv, p[1], p[0]));
            });
            __out(JSON.stringify({bitmap: toBitmap(), min: bounds().min,
                                  dates: dates}));
        """)
        pattern = gg.parse_bitmap(data["bitmap"])
        canvas = gg.calendar_year_canvas(2025, date(2026, 8, 5))
        placement = gg.place(pattern, canvas, data["min"])
        self.assertEqual(sorted(d.isoformat() for d in placement.levels),
                         sorted(data["dates"]))

    def test_stamped_text_matches_the_python_renderer(self):
        """The editor's Stamp button must produce the CLI's glyph layout."""
        data = run_js("""
            var text = "HELLO 2025";
            var glyphs = [];
            for (var i = 0; i < text.length; i++)
                glyphs.push(FONT[text[i].toUpperCase()]);
            var rows = ["", "", "", "", "", "", ""];
            for (var g = 0; g < glyphs.length; g++)
                for (var r = 0; r < 7; r++)
                    rows[r] += (g ? "." : "") + glyphs[g][r];
            __out(JSON.stringify(rows));
        """)
        from font import render_text
        self.assertEqual(data, render_text("HELLO 2025"))


if __name__ == "__main__":
    unittest.main()
