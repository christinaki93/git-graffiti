# gitGraffiti

Draw pixel art on a GitHub contribution graph by generating backdated commits.

## Idea

The contribution graph is a 53x7 grid of days. Each cell's shade comes from how
many commits you made that day. So: pick a bitmap, map each "on" pixel to a
date, and write commits with `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` set to that
date. Push, and the drawing shows up.

## Planned shape

- **Input** — a word rendered in a 7-row pixel font, or an arbitrary bitmap.
- **Layout** — align the pattern to the graph's week columns for a target year
  (columns start on Sunday; the first column may be partial).
- **Intensity** — N commits per lit pixel to hit a given shade tier.
- **Output** — commits into a throwaway repo, with a `--dry-run` that prints an
  ASCII preview of the graph before touching anything.

## Notes

- Only commits on the default branch of a repo you own count toward the graph,
  and the commit email must match a verified email on the account.
- Keep this in a dedicated repo — it rewrites nothing, but it does add a lot of
  noise-commits you probably don't want in a real project.

## Status

Empty scaffold. Nothing implemented yet.
