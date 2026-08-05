"""Embed font.py's glyph table into editor.html.

The editor needs the font in JavaScript, but font.py stays the single source
of truth. Run this after changing font.py:

    python3 embed_font.py

test_editor.py fails if the two ever disagree.
"""

import json
import re

from font import GLYPHS

START = "/*__FONT_DATA__*/"
END = "/*__END_FONT__*/"

# Anchored on both markers. A bare `{...}` pattern runs straight past the empty
# placeholder and swallows the code that follows it.
BLOCK = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)


def main():
    lines = ["{"]
    for char in sorted(GLYPHS):
        rows = ",".join(json.dumps(row) for row in GLYPHS[char])
        lines.append("  %s: [%s]," % (json.dumps(char), rows))
    lines.append("}")
    block = START + "\n".join(lines) + END

    with open("editor.html") as handle:
        html = handle.read()
    if not BLOCK.search(html):
        raise SystemExit("could not find %s ... %s in editor.html"
                         % (START, END))
    html = BLOCK.sub(lambda _: block, html, count=1)
    with open("editor.html", "w") as handle:
        handle.write(html)
    print("embedded %d glyphs" % len(GLYPHS))


if __name__ == "__main__":
    main()
