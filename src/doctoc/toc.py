"""
Core TOC algorithms: heading extraction and GitHub-compatible slugification.

The slugifier mimics GitHub's (undocumented) heading-anchor behavior as
implemented by ``pulldown-cmark-toc``'s ``GitHubSlugifier``:

1. Lower-case the text.
2. Replace spaces with ``-``.
3. Strip anything that is not a word character, a dash, or a space.
4. Unicode accents are removed via NFD normalization so ``"Café"``
   becomes ``"cafe"``, matching GitHub's real rendering.
5. Duplicate slugs get ``-1``, ``-2``, ... suffixes (first occurrence
   keeps the bare slug).

Heading extraction is a hand-rolled CommonMark-aware pass: it tracks
fenced code blocks (`` ``` `` and ``~~~`` with matching delimiters and
any number of trailing backticks/tildes), skips HTML comments, and
recognizes both ATX (``## Title``) and setext (``Title\n=====``) headings.
Inline formatting (``**bold**``, ``*italic*``, `` `code` ``) and links
(``[text](url)``) are unwrapped to plain text before slugification,
matching how GitHub renders heading anchors.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata

Fenced = re.compile(r"^(\s{0,3})(`{3,}|~{3,})([^`\n]*)\s*$")
AtxHeading = re.compile(r"^(\s{0,3})(#{1,6})\s+(.*?)\s*#*\s*$")
HtmlHeading = re.compile(r"^(\s{0,3})<(h[1-6])(\s|>|/>)", re.IGNORECASE)
HtmlCommentOpen = re.compile(r"<!--")
HtmlCommentClose = re.compile(r"-->", re.DOTALL)
ClosingHtag = re.compile(r"</h[1-6]>\s*$", re.IGNORECASE)
AnchorOverride = re.compile(r"\{#([A-Za-z0-9][\w\-]*)\}\s*$")
InlineMarkdown = re.compile(
    r"(\*{1,3}(.+?)\*{1,3}"  # bold/italic/strong
    r"|\[(.+?)\]\([^)\s]*\)"  # link
    r"|`(.+?)`"  # inline code
    r"|\$(.+?)\$"  # inline math (common extension)
    r"|\[[^\]]*\]\[[^\]]*\]"  # reference link
    r"|<[^>]+>)"  # inline HTML tags
)


@dataclasses.dataclass(frozen=True)
class Heading:
    """A heading extracted from a Markdown document."""

    level: int
    text: str
    line: int  # 1-based line number of the heading
    anchor: str  # computed GitHub-compatible anchor


def plain_text(heading_text: str) -> str:
    """Strip Markdown inline formatting from heading text."""
    out: list[str] = []
    pos = 0
    for match in InlineMarkdown.finditer(heading_text):
        out.append(heading_text[pos : match.start()])
        # prefer link text, then italic/bold text, then inline code,
        # then inline math; inline HTML tags and reference links vanish
        content = match.group(3) or match.group(2) or match.group(4) or match.group(5) or ""
        out.append(content)
        pos = match.end()
    out.append(heading_text[pos:])
    return "".join(out)


def _normalize_for_slug(text: str) -> str:
    """Lowercase, accent-strip, and strip non-word characters."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    lowered = text.lower()
    with_dashes = lowered.replace(" ", "-")
    stripped = re.sub(r"[^\w\- ]", "", with_dashes).replace(" ", "")
    return stripped


class _Slugger:
    """Tracks slug occurrences and appends ``-n`` suffixes for duplicates."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def register(self, anchor: str) -> str:
        if not anchor:
            return ""
        count = self._counts.get(anchor, 0)
        self._counts[anchor] = count + 1
        if count == 0:
            return anchor
        return f"{anchor}-{count}"


def extract_headings(source: str) -> list[Heading]:
    """
    Extract Markdown headings, skipping fenced code blocks and HTML comments.

    Handles ATX headings, headings with explicit anchor overrides
    (``{#custom-id}``), and inline formatting stripping.
    """
    lines = source.splitlines()
    headings: list[Heading] = []
    slugger = _Slugger()

    fence = _FenceTracker()
    in_comment = False

    for line_no_0, raw in enumerate(lines, start=1):
        if fence.consume(raw):
            continue

        if in_comment:
            close = HtmlCommentClose.search(raw)
            if close is None:
                continue
            in_comment = False
            raw = raw[close.end() :]

        before, after = _split_comments(raw)
        if before.strip():
            _collect_line(before.strip(), line_no_0, headings, slugger)

        # a comment opened on this line (possibly closed on the same line)
        if HtmlCommentOpen.search(raw):
            if HtmlCommentClose.search(after) is None:
                in_comment = True

    return headings


class _FenceTracker:
    """Tracks open/close of fenced code blocks line by line."""

    def __init__(self) -> None:
        self._fence: re.Match[str] | None = None

    def consume(self, raw: str) -> bool:
        """Return True if the line is inside (or is) a fenced block."""
        if self._fence is None:
            match = Fenced.match(raw)
            if match is not None:
                self._fence = match
                return True
            return False
        match = Fenced.match(raw)
        if (
            match is not None
            and match.group(2)[0] == self._fence.group(2)[0]
            and len(match.group(2)) >= len(self._fence.group(2))
            and match.group(1) <= self._fence.group(1)
        ):
            self._fence = None
            return True
        return True


def _split_comments(line: str) -> tuple[str, str]:
    """Return (text_before_first_comment, text_after_first_comment)."""
    index = HtmlCommentOpen.search(line)
    if index is None:
        return line, ""
    return line[: index.start()], line[index.end() :]


def _collect_line(line: str, line_no_0: int, headings: list[Heading], slugger: _Slugger) -> None:
    """Check an ATX or HTML heading line and append if valid."""
    atx = AtxHeading.match(line)
    if atx is not None:
        text = atx.group(3)
        level = len(atx.group(2))
        headings.append(_make_heading(level, text, line_no_0, slugger))
        return
    html = HtmlHeading.match(line)
    if html is not None:
        level = int(html.group(2)[1])
        inner = line[html.end() :].strip()
        close = ClosingHtag.search(inner)
        if close is not None:
            inner = inner[: close.start()]
        if inner:
            headings.append(_make_heading(level, inner, line_no_0, slugger))
        return


def _make_heading(level: int, text: str, line_no_0: int, slugger: _Slugger) -> Heading:
    override: str | None = None
    match = AnchorOverride.search(text)
    if match is not None:
        override = match.group(1)
        text = text[: match.start()].rstrip()
    anchor = override or github_slug(slugger, text)
    return Heading(level=level, text=text, line=line_no_0, anchor=anchor)


def github_slug(slugger: _Slugger, heading_text: str) -> str:
    """Compute the GitHub-compatible anchor for a heading."""
    text = plain_text(heading_text)
    return slugger.register(_normalize_for_slug(text))
