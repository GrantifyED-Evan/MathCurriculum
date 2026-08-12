"""Parse IM curriculum pages into structured data and readable Markdown.

The IM site uses stable, semantic BEM-style class names (`im-c-card__heading`,
`im-c-row__aside`, ...), so extraction is done against those rather than against
brittle positional heuristics.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Wrapper elements that carry site chrome rather than curriculum content.
_SKIP_CLASS_PATTERNS = re.compile(
    r"im-c-(?:pagination|dropdown|modal|link-menu|marketing-nav|nav|logo|tab|"
    r"footer|breadcrumb|skip-link|search)",
)
_SKIP_TAGS = {"script", "style", "svg", "noscript", "form", "select", "button", "template"}
_BLOCK_TAGS = {"p", "div", "section", "article", "ul", "ol", "table", "tr", "blockquote"}
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# The public site shows a registration pitch where licence-gated content sits.
_GATED_MARKER = re.compile(
    r"(?:can\s+)?click here to register or sign in for free access", re.IGNORECASE
)
_GATED_NOTE = (
    "_[Gated: requires free Kendall Hunt teacher registration — not available "
    "to this agent]_"
)


class _MarkdownExtractor(HTMLParser):
    """Convert the curriculum portion of a page into Markdown."""

    def __init__(self, *, heading_offset: int = 0) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_offset = heading_offset
        self._out: list[str] = []
        self._skip_depth = 0
        self._skip_tag: str | None = None
        self._tag_stack: list[str] = []
        self._list_stack: list[str] = []
        self._pending_heading: int | None = None
        self._in_cell = False
        self._row_cells: list[str] = []
        self._cell_buffer: list[str] = []
        # Set right after a list bullet so a nested block wrapper does not push
        # the item's text onto its own line.
        self._pending_li = False

    # -- helpers -------------------------------------------------------------
    def _emit(self, text: str) -> None:
        if self._in_cell:
            self._cell_buffer.append(text)
        else:
            self._out.append(text)

    def _newline(self) -> None:
        if self._out and not self._out[-1].endswith("\n"):
            self._out.append("\n")

    def _should_skip(self, attrs: dict[str, str]) -> bool:
        classes = attrs.get("class", "")
        if _SKIP_CLASS_PATTERNS.search(classes):
            return True
        return attrs.get("role") in {"navigation", "banner", "contentinfo"}

    # -- HTMLParser hooks ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}

        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return

        if tag in _SKIP_TAGS or self._should_skip(attrs):
            self._skip_depth = 1
            self._skip_tag = tag
            return

        self._tag_stack.append(tag)

        if tag in _HEADING_TAGS:
            self._newline()
            self._out.append("\n")
            self._pending_heading = min(6, _HEADING_TAGS[tag] + self.heading_offset)
            self._out.append("#" * self._pending_heading + " ")
        elif tag in ("ul", "ol"):
            self._newline()
            self._list_stack.append(tag)
        elif tag == "li":
            self._newline()
            depth = max(0, len(self._list_stack) - 1)
            bullet = "1. " if self._list_stack and self._list_stack[-1] == "ol" else "- "
            self._out.append("  " * depth + bullet)
            self._pending_li = True
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "br":
            self._emit("\n")
        elif tag == "img":
            alt = attrs.get("alt", "").strip()
            src = attrs.get("src", "")
            if alt or src:
                self._emit(f"![{alt}]({src})")
        elif tag == "tr":
            self._row_cells = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell_buffer = []
        elif tag in _BLOCK_TAGS:
            if self._pending_li:
                self._pending_li = False
            else:
                self._newline()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    self._skip_tag = None
            return

        if self._tag_stack and tag in self._tag_stack:
            while self._tag_stack and self._tag_stack.pop() != tag:
                pass

        if tag in _HEADING_TAGS:
            self._pending_heading = None
            self._out.append("\n")
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._out.append("\n")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag in ("td", "th"):
            self._in_cell = False
            self._row_cells.append(" ".join("".join(self._cell_buffer).split()))
            self._cell_buffer = []
        elif tag == "tr":
            if self._row_cells:
                self._out.append("\n| " + " | ".join(self._row_cells) + " |")
            self._row_cells = []
        elif tag in _BLOCK_TAGS:
            self._out.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if not text.strip():
            # Preserve a single separating space between inline runs.
            if text == " " and self._out and not self._out[-1].endswith((" ", "\n")):
                self._emit(" ")
            return
        self._pending_li = False
        self._emit(text)

    # -- result --------------------------------------------------------------
    def result(self) -> str:
        text = "".join(self._out)
        text = _GATED_MARKER.sub("", text)
        # Collapse the leftovers of stripped registration pitches.
        text = re.sub(r"(?m)^[ \t]*Teachers with a valid work email address.*$", _GATED_NOTE, text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Drop headings that ended up with no body and no text.
        text = re.sub(r"(?m)^#+\s*$\n?", "", text)
        return text.strip()


def extract_main(page_html: str) -> str:
    """Return the <main> region of a page, or the whole document if absent."""
    match = re.search(r"<main\b[^>]*>(.*?)</main>", page_html, re.S | re.I)
    return match.group(1) if match else page_html


def to_markdown(fragment_html: str, *, heading_offset: int = 0) -> str:
    parser = _MarkdownExtractor(heading_offset=heading_offset)
    parser.feed(fragment_html)
    parser.close()
    return parser.result()


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


# ---------------------------------------------------------------------------
# Structured index parsing
# ---------------------------------------------------------------------------


@dataclass
class UnitSummary:
    number: int
    title: str
    sections: list[str] = field(default_factory=list)


@dataclass
class LessonSummary:
    number: int
    title: str
    section: str = ""


def parse_course_index(page_html: str, family: str, course_number: int) -> list[UnitSummary]:
    """Extract the unit list from a course index page."""
    main = extract_main(page_html)
    href_pattern = re.compile(
        rf'href="/{family}/teachers/{course_number}/(\d+)/index\.html"', re.I
    )

    matches = list(href_pattern.finditer(main))

    units: dict[int, UnitSummary] = {}
    for position, match in enumerate(matches):
        unit_number = int(match.group(1))
        if unit_number in units:
            continue

        # Bound each card by the next unit link so sections never bleed forward.
        end = matches[position + 1].start() if position + 1 < len(matches) else len(main)
        window = main[match.end():end]

        heading = re.search(r'im-c-card__subheading[^>]*>(.*?)</', window, re.S)
        title = _strip_tags(heading.group(1)) if heading else ""

        # The section names are the first list in the card body.
        body = re.search(r"<ul\b[^>]*>(.*?)</ul>", window, re.S)
        sections = (
            [
                _strip_tags(item)
                for item in re.findall(r"<li\b[^>]*>(.*?)</li>", body.group(1), re.S)
            ]
            if body
            else []
        )

        units[unit_number] = UnitSummary(
            number=unit_number, title=title, sections=[s for s in sections if s]
        )

    return [units[key] for key in sorted(units)]


def parse_unit_index(
    page_html: str, family: str, course_number: int, unit_number: int
) -> list[LessonSummary]:
    """Extract the lesson list from a unit index page, keeping section groupings."""
    main = extract_main(page_html)

    # Section headings live in an aside that precedes each group of lesson links.
    section_positions: list[tuple[int, str]] = [
        (m.start(), _strip_tags(m.group(1)))
        for m in re.finditer(
            r'im-c-row__aside.*?<h4[^>]*>(.*?)</h4>', main, re.S
        )
    ]

    def section_for(position: int) -> str:
        current = ""
        for start, name in section_positions:
            if start <= position:
                current = name
            else:
                break
        return current

    lesson_pattern = re.compile(
        rf'href="/{family}/teachers/{course_number}/{unit_number}/(\d+)/'
        rf'(?:preparation|index)\.html"[^>]*>(.*?)</a>',
        re.S | re.I,
    )

    lessons: dict[int, LessonSummary] = {}
    for match in lesson_pattern.finditer(main):
        number = int(match.group(1))
        if number in lessons:
            continue
        spans = re.findall(r"<span[^>]*>(.*?)</span>", match.group(2), re.S)
        # First span is the lesson number badge; the rest is the title.
        title = _strip_tags(" ".join(spans[1:])) if len(spans) > 1 else _strip_tags(match.group(2))
        lessons[number] = LessonSummary(
            number=number, title=title, section=section_for(match.start())
        )

    return [lessons[key] for key in sorted(lessons)]


def parse_lesson(page_html: str) -> dict[str, str]:
    """Return the lesson number, its name, and the body rendered as Markdown.

    Pages label the lesson as `<h1>Lesson 2</h1>` and follow it with the lesson
    name in an `im-c-heading--xlb` paragraph.
    """
    main = extract_main(page_html)

    heading = re.search(r"<h1[^>]*>(.*?)</h1>", main, re.S)
    number_label = _strip_tags(heading.group(1)) if heading else ""

    name = ""
    if heading:
        after = main[heading.end(): heading.end() + 600]
        name_match = re.search(r'im-c-heading--xlb[^>]*>(.*?)</', after, re.S)
        if name_match:
            name = _strip_tags(name_match.group(1))

    title = f"{number_label}: {name}" if number_label and name else (name or number_label)
    return {"title": title, "name": name, "markdown": to_markdown(main)}
