"""Tests for the layout math and pattern handling.

Run with: python3 -m unittest discover
"""

import unittest
from datetime import date, timedelta

import gitgraffiti as gg
from font import UnknownGlyph, render_text


class CanvasTests(unittest.TestCase):
    def test_calendar_year_starts_on_a_sunday(self):
        for year in range(2015, 2036):
            canvas = gg.calendar_year_canvas(year, date(year, 12, 31))
            self.assertEqual(canvas.start.weekday(), 6, year)  # Sunday
            self.assertLessEqual(canvas.start, date(year, 1, 1))
            self.assertLess(date(year, 1, 1) - canvas.start, timedelta(days=7))

    def test_calendar_year_covers_the_whole_year(self):
        for year in range(2015, 2036):
            canvas = gg.calendar_year_canvas(year, date(year, 12, 31))
            self.assertIn(canvas.cols, (53, 54), year)
            last = canvas.cell_date(canvas.cols - 1, 6)
            self.assertGreaterEqual(last, date(year, 12, 31), year)

    def test_2025_layout(self):
        # Jan 1 2025 is a Wednesday, so column 0 starts Sun Dec 29 2024.
        canvas = gg.calendar_year_canvas(2025, date(2025, 12, 31))
        self.assertEqual(canvas.start, date(2024, 12, 29))
        self.assertEqual(canvas.cols, 53)
        self.assertEqual(canvas.cell_date(0, 3), date(2025, 1, 1))

    def test_calendar_year_clamps_to_today(self):
        canvas = gg.calendar_year_canvas(2026, date(2026, 8, 5))
        self.assertEqual(canvas.last, date(2026, 8, 5))
        self.assertFalse(canvas.drawable(date(2026, 8, 6)))
        self.assertFalse(canvas.drawable(date(2025, 12, 31)))
        self.assertTrue(canvas.drawable(date(2026, 1, 1)))

    def test_rolling_window_is_entirely_in_the_past(self):
        today = date(2026, 8, 5)
        canvas = gg.rolling_canvas(today)
        self.assertEqual(canvas.start.weekday(), 6)
        self.assertEqual(canvas.cols, 53)
        self.assertFalse(canvas.drawable(today + timedelta(days=1)))
        self.assertTrue(canvas.drawable(today))
        # 52 whole weeks plus the current partial one.
        self.assertEqual((today - canvas.start).days, 52 * 7 + 3)

    def test_cell_dates_are_unique_and_contiguous(self):
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        seen = [canvas.cell_date(c, r)
                for c in range(canvas.cols) for r in range(gg.ROWS)]
        self.assertEqual(len(set(seen)), len(seen))
        self.assertEqual(max(seen) - min(seen), timedelta(days=len(seen) - 1))


class PatternTests(unittest.TestCase):
    def test_text_pattern_is_seven_rows(self):
        pattern = gg.pattern_from_text("HI")
        self.assertEqual(len(pattern), 7)
        self.assertEqual(gg.pattern_width(pattern), 5 + 1 + 3)

    def test_unknown_glyph_is_loud(self):
        with self.assertRaises(UnknownGlyph):
            render_text("hié")

    def test_text_is_case_insensitive(self):
        self.assertEqual(render_text("abc"), render_text("ABC"))

    def test_bitmap_levels(self):
        pattern = gg.parse_bitmap(".#.\n1 4\n")
        self.assertEqual(len(pattern), 7)
        self.assertIn([0, 4, 0], pattern)
        self.assertIn([1, 0, 4], pattern)

    def test_bitmap_is_centred_vertically(self):
        pattern = gg.parse_bitmap("#\n")
        self.assertEqual([row[0] for row in pattern], [0, 0, 0, 4, 0, 0, 0])

    def test_bitmap_rejects_tall_input(self):
        with self.assertRaises(ValueError):
            gg.parse_bitmap("#\n" * 8)

    def test_bitmap_rejects_junk(self):
        with self.assertRaises(ValueError):
            gg.parse_bitmap("#?#")

    def test_ragged_bitmap_is_padded(self):
        pattern = gg.parse_bitmap("####\n#\n")
        self.assertTrue(all(len(row) == 4 for row in pattern))


class PlacementTests(unittest.TestCase):
    def test_every_lit_pixel_gets_a_distinct_date(self):
        pattern = gg.pattern_from_text("HELLO")
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        placement = gg.place(pattern, canvas, gg.centred_offset(pattern, canvas))
        lit = sum(1 for row in pattern for cell in row if cell)
        self.assertEqual(len(placement.levels), lit)
        self.assertEqual(placement.skipped, 0)

    def test_row_offset_maps_to_weekday(self):
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        pattern = [[0] * 3 for _ in range(7)]
        pattern[2][1] = 4  # row 2 == Tuesday
        placement = gg.place(pattern, canvas, 0)
        day = next(iter(placement.levels))
        self.assertEqual(day.weekday(), 1)  # Monday=0, so Tuesday
        self.assertEqual(day, canvas.cell_date(1, 2))

    def test_pixels_past_the_edge_are_counted_as_skipped(self):
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        pattern = gg.pattern_from_text("A")
        placement = gg.place(pattern, canvas, canvas.cols - 2)
        self.assertGreater(placement.skipped, 0)
        self.assertEqual(placement.lit,
                         len(placement.levels) + placement.skipped)

    def test_future_dates_are_never_drawn(self):
        today = date(2026, 8, 5)
        canvas = gg.calendar_year_canvas(2026, today)
        pattern = [[4] * canvas.cols for _ in range(7)]
        placement = gg.place(pattern, canvas, 0)
        self.assertTrue(all(day <= today for day in placement.levels))
        self.assertGreater(placement.skipped, 0)


class CommitPlanTests(unittest.TestCase):
    def test_plan_is_chronological_and_scaled(self):
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        pattern = [[0] * 4 for _ in range(7)]
        pattern[0][0] = 1
        pattern[6][3] = 4
        plan = gg.commit_plan(gg.place(pattern, canvas, 0), per_level=3)
        self.assertEqual([count for _, count in plan], [3, 12])
        self.assertEqual([day for day, _ in plan],
                         sorted(day for day, _ in plan))


class PreviewTests(unittest.TestCase):
    def test_preview_shape(self):
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        pattern = gg.pattern_from_text("HI")
        placement = gg.place(pattern, canvas, 0)
        lines = gg.render_preview(placement, color=False).splitlines()
        self.assertEqual(len(lines), gg.ROWS + 1)  # month header + 7 days
        self.assertEqual(len(set(len(line.rstrip()) > 0 for line in lines)), 1)

    def test_preview_marks_lit_days(self):
        canvas = gg.rolling_canvas(date(2026, 8, 5))
        pattern = [[0] * 3 for _ in range(7)]
        pattern[0][0] = 4
        placement = gg.place(pattern, canvas, 0)
        self.assertIn("#", gg.render_preview(placement, color=False))


if __name__ == "__main__":
    unittest.main()
