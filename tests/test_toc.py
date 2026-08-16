"""Tests for the core slugification and heading extraction algorithms."""

from __future__ import annotations

from doctoc.toc import (
    Heading,
    _normalize_for_slug,
    _Slugger,
    extract_headings,
    github_slug,
    plain_text,
)

# ---------------------------------------------------------------------------
# Slugification (GitHub-compatible)
# ---------------------------------------------------------------------------


def test_slug_basic() -> None:
    assert _normalize_for_slug("Installation") == "installation"


def test_slug_spaces_to_dashes() -> None:
    assert _normalize_for_slug("Getting Started Guide") == "getting-started-guide"


def test_slug_strips_special_chars() -> None:
    assert _normalize_for_slug("What is 'it'?") == "what-is-it"


def test_slug_preserves_underscores_and_dashes() -> None:
    assert _normalize_for_slug("my_feature-name") == "my_feature-name"


def test_slug_accent_removal() -> None:
    assert _normalize_for_slug("Café Résumé naïve") == "cafe-resume-naive"


def test_slug_empty_after_strip() -> None:
    assert _normalize_for_slug("!!!") == ""


def test_slug_keeps_unicode_word_chars() -> None:
    # Python's \w matches unicode word characters (CJK included),
    # so unicode letters survive slugification (GitHub keeps them too).
    assert _normalize_for_slug("日本語") == "日本語"


def test_dedup_suffixes() -> None:
    slugger = _Slugger()
    assert slugger.register("usage") == "usage"
    assert slugger.register("usage") == "usage-1"
    assert slugger.register("usage") == "usage-2"
    assert slugger.register("other") == "other"


def test_dedup_empty_anchor() -> None:
    slugger = _Slugger()
    assert slugger.register("") == ""
    assert slugger.register("") == ""


def test_github_slug_integrates_plain_text() -> None:
    slugger = _Slugger()
    assert github_slug(slugger, "**Bold** heading") == "bold-heading"
    assert github_slug(slugger, "[Link](https://x.com) here") == "link-here"
    assert github_slug(slugger, "`code` heading") == "code-heading"


def test_anchor_override_not_part_of_slug() -> None:
    headings = extract_headings("## Title {#manual}\n")
    assert headings == [Heading(level=2, text="Title", line=1, anchor="manual")]


def test_plain_text_strips_formatting() -> None:
    assert plain_text("**bold**") == "bold"
    assert plain_text("[link](url)") == "link"
    assert plain_text("`code`") == "code"
    assert plain_text("$math$") == "math"
    assert plain_text("<br>html</br>") == "html"
    assert plain_text("[ref][id]") == ""
    assert plain_text("mixed **a** and `b`") == "mixed a and b"


# ---------------------------------------------------------------------------
# Heading extraction
# ---------------------------------------------------------------------------


def test_atx_headings() -> None:
    src = "# One\n## Two\n### Three\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["One", "Two", "Three"]
    assert [h.level for h in headings] == [1, 2, 3]
    assert [h.line for h in headings] == [1, 2, 3]


def test_atx_closing_hashes() -> None:
    headings = extract_headings("## Title ### \n")
    assert headings[0].text == "Title"


def test_atx_no_space_is_not_heading() -> None:
    headings = extract_headings("#nospace\n")
    assert headings == []


def test_seven_hashes_not_heading() -> None:
    headings = extract_headings("####### too deep\n")
    assert headings == []


def test_fenced_code_headings_ignored() -> None:
    src = "```python\n## hidden\n```\n## visible\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["visible"]


def test_fenced_tilde_code_headings_ignored() -> None:
    src = "~~~\n## hidden\n~~~\n## visible\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["visible"]


def test_fenced_longer_closer_closes() -> None:
    src = "```\n## hidden\n````\n## visible\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["visible"]


def test_fenced_shorter_closer_does_not_close() -> None:
    src = "````\n## hidden\n```\n## also hidden\n"
    headings = extract_headings(src)
    assert headings == []


def test_fenced_until_eof() -> None:
    src = "## first\n```\n## hidden at eof\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["first"]


def test_fenced_different_kind_does_not_close() -> None:
    src = "```\n## hidden\n~~~\n## also hidden\n"
    headings = extract_headings(src)
    assert headings == []


def test_html_comment_headings_ignored() -> None:
    src = "<!--\n## hidden\n-->\n## visible\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["visible"]


def test_html_comment_same_line() -> None:
    src = "## visible <!-- comment -->\n"
    headings = extract_headings(src)
    assert headings[0].text == "visible"


def test_heading_before_multiline_comment() -> None:
    src = "## before <!-- comment\n## hidden inside\n-->\n## after\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["before", "after"]


def test_heading_around_same_line_comment() -> None:
    src = "## before <!-- ## hidden -->\n## after\n"
    headings = extract_headings(src)
    assert [h.text for h in headings] == ["before", "after"]


def test_inline_formatting_in_heading() -> None:
    src = "## **bold** and [link](url)\n"
    headings = extract_headings(src)
    assert headings[0].text == "**bold** and [link](url)"
    assert headings[0].anchor == "bold-and-link"


def test_link_in_heading_anchor() -> None:
    src = "## [Link](https://example.com/a) text\n"
    headings = extract_headings(src)
    assert headings[0].anchor == "link-text"


def test_duplicate_headings_dedup() -> None:
    src = "## Usage\n## Usage\n## Usage\n"
    headings = extract_headings(src)
    assert [h.anchor for h in headings] == ["usage", "usage-1", "usage-2"]


def test_line_numbers_tracked() -> None:
    src = "a\nb\n## Third\n"
    headings = extract_headings(src)
    assert headings[0].line == 3


def test_empty_source() -> None:
    assert extract_headings("") == []


def test_no_headings() -> None:
    assert extract_headings("just text\nand more\n") == []


def test_deep_nesting_preserved() -> None:
    src = "###### deepest\n"
    headings = extract_headings(src)
    assert headings[0].level == 6


def test_mid_text_hash_is_heading() -> None:
    # CommonMark accepts '#' mid-text in ATX headings; the hash becomes
    # part of the heading text (matches GitHub rendering).
    src = "## title # with hash mid\n"
    headings = extract_headings(src)
    assert headings[0].text == "title # with hash mid"
    assert headings[0].anchor == "title--with-hash-mid"


def test_mid_text_hash_with_closing_ok() -> None:
    src = "## title # with hash ## \n"
    headings = extract_headings(src)
    assert headings[0].text == "title # with hash"


def test_anchor_override_custom_id() -> None:
    src = "## Title {#custom-id}\n"
    headings = extract_headings(src)
    assert headings[0].text == "Title"
    assert headings[0].anchor == "custom-id"


def test_anchor_override_with_formatting() -> None:
    src = "## **Bold** {#bold}\n"
    headings = extract_headings(src)
    assert headings[0].anchor == "bold"
