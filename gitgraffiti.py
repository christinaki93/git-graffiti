#!/usr/bin/env python3
"""gitGraffiti - draw pixel art on a GitHub contribution graph.

The graph is a grid of weeks (columns) by weekdays (rows, Sunday at the top).
A cell's shade comes from how many commits you authored that day, so drawing
means picking a date per lit pixel and writing backdated commits there.

Nothing is written unless you pass --commit; the default is a preview.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from font import UnknownGlyph, render_text

ROWS = 7  # Sunday .. Saturday
MAX_LEVEL = 4
DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""]

# GitHub's contribution palette, level 0 through 4.
LEVEL_RGB = [
    (48, 54, 61),
    (14, 68, 41),
    (0, 109, 50),
    (38, 166, 65),
    (57, 211, 83),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# patterns
# --------------------------------------------------------------------------

def parse_bitmap(text):
    """Parse a bitmap file into rows of levels (0-4).

    '.', ' ' and '0' are unlit. '#', '*' and 'x' are full brightness. Digits
    '1'-'4' set an explicit shade. Fewer than 7 rows are centred vertically.
    """
    lines = [line.rstrip("\n") for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ValueError("bitmap is empty")
    if len(lines) > ROWS:
        raise ValueError("bitmap has %d rows; the graph is only %d tall"
                         % (len(lines), ROWS))

    width = max(len(line) for line in lines)
    grid = []
    for line in lines:
        row = []
        for char in line.ljust(width):
            if char in ".0 ":
                row.append(0)
            elif char in "#*xX":
                row.append(MAX_LEVEL)
            elif char in "1234":
                row.append(int(char))
            else:
                raise ValueError("unexpected character %r in bitmap" % char)
        grid.append(row)

    pad = ROWS - len(grid)
    top = pad // 2
    blank = [0] * width
    return [list(blank) for _ in range(top)] + grid + \
           [list(blank) for _ in range(pad - top)]


def pattern_from_text(text):
    """Render text to a level grid at full brightness."""
    return [[MAX_LEVEL if c == "#" else 0 for c in row]
            for row in render_text(text)]


def pattern_width(pattern):
    return max((len(row) for row in pattern), default=0)


# --------------------------------------------------------------------------
# the canvas
# --------------------------------------------------------------------------

def _sunday_on_or_before(day):
    # date.weekday() is Mon=0 .. Sun=6; shift so Sunday is 0.
    return day - timedelta(days=(day.weekday() + 1) % 7)


@dataclass
class Canvas:
    """The drawable grid: column 0 starts on `start`, a Sunday."""

    start: date
    cols: int
    first: date  # earliest date that counts for this view
    last: date   # latest date we are willing to commit to
    label: str

    def cell_date(self, col, row):
        return self.start + timedelta(days=col * ROWS + row)

    def drawable(self, day):
        return self.first <= day <= self.last


def calendar_year_canvas(year, today):
    """The graph as GitHub renders it for a single calendar year."""
    jan1 = date(year, 1, 1)
    dec31 = date(year, 12, 31)
    start = _sunday_on_or_before(jan1)
    cols = (_sunday_on_or_before(dec31) - start).days // ROWS + 1
    return Canvas(start=start, cols=cols, first=jan1,
                  last=min(dec31, today), label=str(year))


def rolling_canvas(today):
    """The trailing 53-week window a profile page shows by default."""
    this_week = _sunday_on_or_before(today)
    start = this_week - timedelta(weeks=52)
    return Canvas(start=start, cols=53, first=start, last=today,
                  label="%s to %s" % (start.isoformat(), today.isoformat()))


# --------------------------------------------------------------------------
# placement
# --------------------------------------------------------------------------

@dataclass
class Placement:
    canvas: Canvas
    levels: dict          # date -> level (1-4)
    offset: int
    lit: int              # lit pixels in the pattern
    skipped: int          # lit pixels that fell outside the drawable range


def place(pattern, canvas, offset):
    """Map a pattern onto the canvas at column `offset`."""
    levels = {}
    lit = skipped = 0
    for row, cells in enumerate(pattern):
        for col, level in enumerate(cells):
            if not level:
                continue
            lit += 1
            target = offset + col
            if not 0 <= target < canvas.cols:
                skipped += 1
                continue
            day = canvas.cell_date(target, row)
            if not canvas.drawable(day):
                skipped += 1
                continue
            levels[day] = level
    return Placement(canvas=canvas, levels=levels, offset=offset,
                     lit=lit, skipped=skipped)


def centred_offset(pattern, canvas):
    return max(0, (canvas.cols - pattern_width(pattern)) // 2)


# --------------------------------------------------------------------------
# preview
# --------------------------------------------------------------------------

def _shade(level, color):
    if not color:
        return " .-+#"[level]
    r, g, b = LEVEL_RGB[level]
    return "\x1b[38;2;%d;%d;%dm■\x1b[0m" % (r, g, b)


def _month_header(canvas, gutter):
    """Month labels above the grid, one per run of columns in that month.

    A run narrower than its label is left unlabelled — that is usually the
    partial week at the start of a calendar-year view, and labelling it would
    crowd out the month that follows.
    """
    header = [" "] * canvas.cols
    runs = []
    for col in range(canvas.cols):
        month = canvas.cell_date(col, 0).month
        if runs and runs[-1][0] == month:
            runs[-1][2] = col
        else:
            runs.append([month, col, col])

    for month, start, end in runs:
        label = MONTHS[month - 1]
        if end - start + 1 < len(label) or start + len(label) > canvas.cols:
            continue
        if any(header[start + i] != " " for i in range(len(label))):
            continue
        for i, char in enumerate(label):
            header[start + i] = char
    return " " * gutter + "".join(header)


def render_preview(placement, color=True):
    canvas = placement.canvas
    gutter = max(len(d) for d in DAY_LABELS) + 1
    lines = [_month_header(canvas, gutter)]
    for row in range(ROWS):
        cells = []
        for col in range(canvas.cols):
            day = canvas.cell_date(col, row)
            if not canvas.drawable(day):
                cells.append(" ")
            else:
                cells.append(_shade(placement.levels.get(day, 0), color))
        lines.append(DAY_LABELS[row].ljust(gutter) + "".join(cells))
    return "\n".join(lines)


def render_legend(color=True):
    return "less " + " ".join(_shade(i, color) for i in range(MAX_LEVEL + 1)) \
        + " more"


# --------------------------------------------------------------------------
# committing
# --------------------------------------------------------------------------

def git(repo, *args, **kwargs):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=False, **kwargs)


def repo_has_commits(repo):
    return git(repo, "rev-parse", "--verify", "HEAD").returncode == 0


def ensure_repo(repo):
    """Create and initialise `repo` if it does not exist yet."""
    created = False
    if not os.path.isdir(os.path.join(repo, ".git")):
        os.makedirs(repo, exist_ok=True)
        result = subprocess.run(["git", "init", "-b", "main", repo],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("git init failed: " + result.stderr.strip())
        created = True
    return created


def commit_plan(placement, per_level):
    """(date, count) pairs in chronological order."""
    return [(day, level * per_level)
            for day, level in sorted(placement.levels.items())]


def write_commits(repo, plan, message, author=None, email=None, quiet=False):
    """Write the backdated commits. Returns the number written."""
    log = os.path.join(repo, "graffiti.log")
    total = sum(count for _, count in plan)
    written = 0
    env = dict(os.environ)
    if author:
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = author
    if email:
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = email

    for day, count in plan:
        # Noon UTC keeps a commit from sliding into an adjacent day.
        stamp = "%s 12:00:00 +0000" % day.isoformat()
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
        for n in range(count):
            with open(log, "a") as handle:
                handle.write("%s %d\n" % (day.isoformat(), n))
            result = subprocess.run(
                ["git", "-C", repo, "add", "graffiti.log"],
                capture_output=True, text=True, env=env)
            if result.returncode != 0:
                raise RuntimeError("git add failed: " + result.stderr.strip())
            result = subprocess.run(
                ["git", "-C", repo, "commit", "-m",
                 message.format(date=day.isoformat(), n=n + 1)],
                capture_output=True, text=True, env=env)
            if result.returncode != 0:
                raise RuntimeError("git commit failed: " + result.stderr.strip())
            written += 1
            if not quiet and written % 25 == 0:
                sys.stderr.write("\r  %d/%d commits" % (written, total))
                sys.stderr.flush()
    if not quiet and total:
        sys.stderr.write("\r  %d/%d commits\n" % (written, total))
    return written


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def parse_offset(value):
    if value == "center":
        return value
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("offset must be an integer or 'center'")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="gitgraffiti",
        description="Draw pixel art on a GitHub contribution graph.",
        epilog="Previews by default; pass --commit to actually write commits.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="text to draw, e.g. --text HELLO")
    source.add_argument("--bitmap", help="path to a bitmap file")

    parser.add_argument("--year", type=int,
                        help="draw on a calendar year instead of the trailing "
                             "53-week window")
    parser.add_argument("--offset", type=parse_offset, default="center",
                        help="starting column, or 'center' (default)")
    parser.add_argument("--per-level", type=int, default=3, metavar="N",
                        help="commits per shade level (default: 3)")
    parser.add_argument("--no-color", action="store_true",
                        help="ASCII preview instead of colored blocks")

    parser.add_argument("--commit", action="store_true",
                        help="actually write the commits")
    parser.add_argument("--repo", help="repository to commit into "
                                       "(created if missing)")
    parser.add_argument("--allow-existing", action="store_true",
                        help="permit committing into a repo that already has "
                             "history")
    parser.add_argument("--author", help="override commit author name")
    parser.add_argument("--email", help="override commit author email "
                                        "(must be verified on GitHub)")
    parser.add_argument("--message", default="gitGraffiti {date} #{n}",
                        help="commit message template; {date} and {n} are "
                             "substituted")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    today = date.today()

    try:
        if args.text:
            pattern = pattern_from_text(args.text)
        else:
            with open(args.bitmap) as handle:
                pattern = parse_bitmap(handle.read())
    except (UnknownGlyph, ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    canvas = (calendar_year_canvas(args.year, today) if args.year
              else rolling_canvas(today))
    offset = (centred_offset(pattern, canvas) if args.offset == "center"
              else args.offset)
    placement = place(pattern, canvas, offset)

    if args.per_level < 1:
        print("error: --per-level must be at least 1", file=sys.stderr)
        return 2

    color = not args.no_color and sys.stdout.isatty()
    plan = commit_plan(placement, args.per_level)
    total = sum(count for _, count in plan)

    print(render_preview(placement, color))
    print()
    print("  view      %s" % canvas.label)
    print("  pattern   %d x %d, placed at column %d"
          % (pattern_width(pattern), ROWS, offset))
    print("  days      %d lit" % len(placement.levels))
    print("  commits   %d (%d per shade level)" % (total, args.per_level))
    if plan:
        print("  range     %s to %s" % (plan[0][0], plan[-1][0]))
    print("  %s" % render_legend(color))

    if placement.skipped:
        print("\nwarning: %d lit pixel(s) fell outside the graph and were "
              "dropped; try a smaller pattern or a different --offset"
              % placement.skipped, file=sys.stderr)
    if not placement.levels:
        print("\nerror: nothing to draw", file=sys.stderr)
        return 1

    if not args.commit:
        print("\nPreview only. Re-run with --commit --repo <path> to write.")
        return 0

    if not args.repo:
        print("\nerror: --commit requires --repo", file=sys.stderr)
        return 2

    repo = os.path.abspath(args.repo)
    try:
        created = ensure_repo(repo)
    except RuntimeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if created:
        print("\nInitialised a new repository at %s" % repo)
    elif repo_has_commits(repo) and not args.allow_existing:
        print("\nerror: %s already has commits. gitGraffiti adds hundreds of "
              "noise commits, so point it at a throwaway repo, or pass "
              "--allow-existing if you meant this one." % repo, file=sys.stderr)
        return 1

    print("\nWriting %d commits into %s" % (total, repo))
    try:
        written = write_commits(repo, plan, args.message,
                                author=args.author, email=args.email)
    except RuntimeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    print("Wrote %d commits." % written)
    print("\nNext: create an empty repo on GitHub, then\n"
          "  git -C %s remote add origin <url>\n"
          "  git -C %s push -u origin main" % (repo, repo))
    print("The graph only counts commits on the default branch of a repo you "
          "own, authored by a verified email on your account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
