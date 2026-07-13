"""
HTML -> readable text, using only the standard-library HTML parser.

Drops script/style/noscript/template/svg, inserts line breaks at block
boundaries, collapses whitespace, and pulls the <title>. Good enough to hand a
page's visible content to an LLM without bringing in BeautifulSoup/lxml.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "header", "footer", "nav", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    "pre", "hr", "td", "th",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title += data
            return
        if data.strip():
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        # Collapse runs of spaces/tabs, then squeeze blank lines.
        raw = re.sub(r"[ \t\f\v]+", " ", raw)
        lines = [ln.strip() for ln in raw.split("\n")]
        out: list[str] = []
        blank = False
        for ln in lines:
            if ln:
                out.append(ln)
                blank = False
            elif not blank:
                out.append("")
                blank = True
        return "\n".join(out).strip()


def html_to_text(html: str) -> tuple[str, str]:
    """Return (title, cleaned_text)."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        # Malformed HTML — return whatever was parsed so far.
        pass
    return parser.title.strip(), parser.text()
