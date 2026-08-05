# gitGraffiti

Draw pixel art on a GitHub contribution graph by generating backdated commits.

Python 3, standard library only. No dependencies, nothing to install.

## How it works

The contribution graph is a grid of weeks (columns) by weekdays (rows, Sunday
at the top). A cell's shade comes from how many commits you authored that day.
So gitGraffiti renders your text or bitmap to a 7-row pixel grid, maps each lit
pixel to a date, and writes commits with `GIT_AUTHOR_DATE` and
`GIT_COMMITTER_DATE` set to that date.

**Nothing is written unless you pass `--commit`.** The default is a preview.

## Usage

Preview some text on the trailing 53-week window (what your profile shows):

```
python3 gitgraffiti.py --text "HELLO"
```

```
    Aug  Sep Oct Nov  Dec Jan Feb Mar  Apr May  Jun Jul
                #   # ##### #     #      ###
Mon             #   # #     #     #     #   #
                #   # #     #     #     #   #
Wed             ##### ####  #     #     #   #
                #   # #     #     #     #   #
Fri             #   # #     #     #     #   #
                #   # ##### ##### #####  ###

  view      2025-08-03 to 2026-08-05
  pattern   29 x 7, placed at column 12
  days      73 lit
  commits   876 (3 per shade level)
  range     2025-10-26 to 2026-05-15
```

Draw a bitmap on a specific calendar year, then actually write it:

```
python3 gitgraffiti.py --bitmap examples/heart.txt --year 2025
python3 gitgraffiti.py --bitmap examples/heart.txt --year 2025 \
    --commit --repo ~/code/graffiti-out
```

Then push it, on the default branch of a repo you own:

```
git -C ~/code/graffiti-out remote add origin git@github.com:you/graffiti.git
git -C ~/code/graffiti-out push -u origin main
```

### Options

| Flag | Meaning |
| --- | --- |
| `--text TEXT` | Draw text using the built-in 7-row font. |
| `--bitmap FILE` | Draw an arbitrary bitmap (see below). |
| `--year YYYY` | Use a calendar year instead of the trailing 53 weeks. |
| `--offset N` | Starting column; `center` (the default) centres the art. |
| `--per-level N` | Commits per shade level, default 3. Level 4 → 12 commits. |
| `--commit` | Actually write commits. Without it, you get a preview. |
| `--repo PATH` | Where to commit. Created and `git init`ed if missing. |
| `--allow-existing` | Permit committing into a repo that already has history. |
| `--author` / `--email` | Override the commit identity. |
| `--message` | Message template; `{date}` and `{n}` are substituted. |
| `--no-color` | ASCII preview instead of colored blocks. |

### Bitmap format

Up to 7 rows of text. `.`, space and `0` are unlit; `#`, `*` and `x` are full
brightness; `1`-`4` set an explicit shade. Short bitmaps are centred
vertically, ragged rows are padded. See `examples/`.

```
.###...###.
###########
###########
.#########.
..#######..
...#####...
.....#.....
```

## Things that will bite you

- **Use a throwaway repo.** This writes hundreds of noise commits. gitGraffiti
  refuses to commit into a repo that already has history unless you pass
  `--allow-existing`.
- **The email must be verified on your GitHub account**, or the commits will
  not count toward the graph. Check what you are using with
  `git config user.email`.
- **Only the default branch of a repo you own counts.**
- **Shading is relative.** GitHub buckets shades against your busiest day in
  the window, so your real commits can wash the art out. Raise `--per-level`
  if the drawing looks faint.
- **No future dates.** Cells past today are dropped and reported as skipped.
  This is why the default view is the trailing 53 weeks rather than the current
  calendar year.

## Removing it

Delete the repo, or delete the remote branch — the contributions disappear
along with the commits.

## Tests

```
python3 -m unittest discover
```
