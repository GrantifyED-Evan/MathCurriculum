"""Turn accessim.org pages into structured data.

accessim.org is a Next.js site that streams its content: the initial HTML holds
empty `<template id="B:n">` / `<template id="P:n">` placeholders, and the real
markup sits later in the page inside `<div hidden id="S:n">` blocks that a script
swaps in. We do that swap here, then flatten the main content into a list of
blocks (headings, paragraphs, list items, images) that the extractors walk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape as _html_unescape
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Streaming resolution and flattening
# ---------------------------------------------------------------------------

_SEGMENT_OPEN = re.compile(r'<div hidden id="S:([0-9a-z]+)">')
_DIV_TAG = re.compile(r"<(/?)div\b[^>]*>")
_TEMPLATE = re.compile(r'<template id="([BP]:[0-9a-z]+)"></template>')
_SWAP_CALL = re.compile(r'\$R[CS]\("([BP]:[0-9a-z]+)","S:([0-9a-z]+)"')


def _segments(html: str) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for m in _SEGMENT_OPEN.finditer(html):
        depth = 1
        for tag in _DIV_TAG.finditer(html, m.end()):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                out[m.group(1)] = (m.start(), html[m.end() : tag.start()])
                break
    return out


def resolve_stream(html: str) -> str:
    """Return the page with every streamed segment placed where it renders."""
    swaps = {placeholder: seg for placeholder, seg in _SWAP_CALL.findall(html)}
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    segments = _segments(html)
    first = min((start for start, _ in segments.values()), default=len(html))
    doc = html[:first]

    def swap(m: re.Match) -> str:
        key = m.group(1)
        seg = segments.get(swaps.get(key, key[2:]))
        return seg[1] if seg else ""

    for _ in range(50):
        new = _TEMPLATE.sub(swap, doc)
        if new == doc:
            break
        doc = new
    return doc


_MATH = re.compile(r"<mjx-container\b.*?</mjx-container>", re.S)
_MATH_LATEX = re.compile(r'data-mml-node="math"[^>]*?data-latex="([^"]*)"')
_LATEX_SYMBOLS = {
    r"\cdot": "·", r"\times": "×", r"\div": "÷", r"\pi": "π", r"\le": "≤", r"\ge": "≥",
    r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\approx": "≈", r"\pm": "±", r"\circ": "°",
    r"\degree": "°", r"\theta": "θ", r"\angle": "∠", r"\triangle": "△", r"\infty": "∞",
    r"\%": "%", r"\$": "$", r"\dots": "…", r"\ldots": "…", r"\to": "→", r"\sim": "~",
    r"\cong": "≅", r"\parallel": "∥", r"\perp": "⊥",
}


def latex_to_text(latex: str) -> str:
    """Render the LaTeX the site embeds for each formula as readable plain text."""
    import html as _html

    t = _html.unescape(latex)
    t = t.replace("\\(", "").replace("\\)", "")
    t = re.sub(r"(\d)\s*(?=\\[dt]?frac)", r"\1 ", t)
    t = re.sub(r"\\(?:begin|end)\s*\{[^{}]*\}", " ", t)
    t = re.sub(r"\s*\\\\\s*", "; ", t).replace("&", "")
    t = re.sub(r"\\[dt]?frac\s*(\d)\s*(\d)", r"\1/\2", t)
    t = re.sub(r"\\(?:text|textrm|mathrm|textit|mathit|mathbf|operatorname)\s*\{([^{}]*)\}", r"\1", t)
    for _ in range(5):
        t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", _frac, t)
        t = re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}", r"\1√(\2)", t)
        t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", _sqrt, t)
        t = re.sub(r"\\overline\s*\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\^\s*\{\\circ\}|\^\\circ", "°", t)
    for k in sorted(_LATEX_SYMBOLS, key=len, reverse=True):
        t = re.sub(re.escape(k) + r"(?![A-Za-z])", lambda _m, v=_LATEX_SYMBOLS[k]: v, t)
    t = re.sub(r"\\(left|right|big|Big|displaystyle)\b", "", t)
    t = re.sub(r"\\[,;:! ]", " ", t)
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)
    t = re.sub(r"\\(?:text|textrm|mathrm|mathit|mathbf|boldsymbol|bold|bf|operatorname)(?![A-Za-z])", "", t)
    t = re.sub(r"\\([A-Za-z]+)", r"\1", t)
    t = t.replace("\\{", "\x00").replace("\\}", "\x01")
    t = re.sub(r"[{}]", "", t).replace("\x00", "{").replace("\x01", "}")
    return " ".join(t.split())


def _frac(m: re.Match) -> str:
    a, b = m.group(1).strip(), m.group(2).strip()
    wrap = lambda x: x if re.fullmatch(r"[\w.]+", x) else f"({x})"  # noqa: E731
    return f"{wrap(a)}/{wrap(b)}"


def _sqrt(m: re.Match) -> str:
    x = m.group(1).strip()
    return f"√{x}" if re.fullmatch(r"[\w.]+", x) else f"√({x})"


def _math_to_text(m: re.Match) -> str:
    found = _MATH_LATEX.search(m.group(0))
    return latex_to_text(found.group(1)) if found else ""


@dataclass
class Block:
    kind: str  # h1..h5, p, li, img
    text: str


_BLOCK_TAGS = {"p", "li", "div", "h1", "h2", "h3", "h4", "h5", "tr", "td", "figure", "br"}
_SKIP_TAGS = {"svg", "style", "button", "template"}


class _Flattener(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.kind = "p"
        self.buf: list[str] = []
        self.skip = 0

    def _flush(self) -> None:
        text = " ".join("".join(self.buf).split())
        if text:
            self.blocks.append(Block(self.kind, text))
        self.buf = []
        self.kind = "p"

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self.skip += 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            if tag in {"h1", "h2", "h3", "h4", "h5", "li"}:
                self.kind = tag
        elif tag == "img" and not self.skip:
            alt = _html_unescape(_html_unescape(dict(attrs).get("alt") or ""))
            alt = re.sub(r"\\\((.*?)\\\)", lambda m: latex_to_text(m.group(1)), alt)
            alt = " ".join(re.sub(r"<[^>]+>", " ", alt).split())
            if alt and alt != "Course Icon":
                self._flush()
                self.blocks.append(Block("img", alt))

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


_NOISE = {"Loading...", "View Full Standard", "None"}


def flatten(html: str) -> list[Block]:
    """Resolve the stream and return the main-content blocks of a page."""
    doc = _MATH.sub(_math_to_text, resolve_stream(html))
    start = doc.find("layout__main")
    if start != -1:
        doc = doc[doc.rfind("<", 0, start) :]
    parser = _Flattener()
    parser.feed(doc)
    parser.close()
    blocks = []
    for b in parser.blocks:
        if b.text in _NOISE or re.match(r"^(Sign in )?to access ", b.text):
            continue
        if b.kind == "h2" and b.text.startswith("Have feedback on the curriculum"):
            break
        blocks.append(b)
    return blocks


def _sections(blocks: list[Block], level: str) -> list[tuple[str, list[Block]]]:
    """Split blocks on headings of `level`, returning (heading, body) pairs."""
    out: list[tuple[str, list[Block]]] = [("", [])]
    for b in blocks:
        if b.kind == level:
            out.append((b.text, []))
        else:
            out[-1][1].append(b)
    return out


def _texts(blocks: list[Block]) -> list[str]:
    return [b.text for b in blocks]


def _to_lines(blocks: list[Block]) -> list[str]:
    """Body blocks as display lines: list items get a bullet, images a marker."""
    lines = []
    for b in blocks:
        if b.kind == "li":
            lines.append("• " + b.text)
        elif b.kind == "img":
            lines.append(f"[Image: {b.text}]")
        elif b.kind in {"h4", "h5"}:
            lines.append(b.text + ":")
        else:
            lines.append(b.text)
    return lines


# ---------------------------------------------------------------------------
# Course and unit pages
# ---------------------------------------------------------------------------

_LESSON_LINK = re.compile(
    r'<a[^>]*href="(?P<path>/[^"?]*/unit-(?P<unit>\d+)/section-(?P<section>[a-z])/'
    r'lesson-(?P<lesson>\d+))/preparation[^"]*"[^>]*>(?P<body>.*?)</a>',
    re.S,
)


def unit_title(html: str) -> str:
    for b in flatten(html):
        if b.kind == "h1":
            return b.text
    return ""


def unit_lessons(html: str) -> list[dict]:
    """Lessons linked from a unit page, in course order."""
    doc = resolve_stream(html)
    seen: dict[int, dict] = {}
    for m in _LESSON_LINK.finditer(doc):
        number = int(m.group("lesson"))
        if number in seen:
            continue
        parts = [p.strip() for p in re.sub(r"<[^>]+>", "\n", m.group("body")).split("\n")]
        parts = [p for p in parts if p and not p.isdigit()]
        seen[number] = {
            "number": number,
            "section": m.group("section"),
            "path": m.group("path"),
            "title": _unescape(parts[0]) if parts else f"Lesson {number}",
            "goal": _unescape(parts[1]) if len(parts) > 1 else "",
        }
    return [seen[k] for k in sorted(seen)]


def _unescape(text: str) -> str:
    import html as _html

    return " ".join(_html.unescape(text).split())


# ---------------------------------------------------------------------------
# Preparation page
# ---------------------------------------------------------------------------


@dataclass
class Preparation:
    title: str = ""
    narrative: list[str] = field(default_factory=list)
    learning_goals: list[str] = field(default_factory=list)
    student_goal: str = ""
    student_targets: list[str] = field(default_factory=list)
    materials: list[tuple[str, list[str]]] = field(default_factory=list)
    required_prep: list[str] = field(default_factory=list)
    standards: dict[str, list[str]] = field(default_factory=dict)
    glossary: list[tuple[str, str]] = field(default_factory=list)


def _standards(blocks: list[Block]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for b in blocks:
        if b.kind == "p" and b.text in {"Building On", "Addressing", "Building Toward"}:
            current = b.text
            out.setdefault(current, [])
        elif b.kind == "h5" and current:
            if b.text not in out[current]:
                out[current].append(b.text)
    return {k: v for k, v in out.items() if v}


def parse_preparation(html: str) -> Preparation:
    blocks = flatten(html)
    prep = Preparation()
    for b in blocks:
        if b.kind == "h1":
            prep.title = b.text
            break
    for heading, body in _sections(blocks, "h2"):
        if heading == "Lesson Narrative":
            prep.narrative = _texts(body)
        elif heading == "Learning Goals":
            for sub, sub_body in _sections(body, "h3"):
                if sub == "":
                    prep.learning_goals = [t for t in _texts(sub_body) if t != "*"]
                elif sub == "Student-Facing Goal":
                    prep.student_goal = " ".join(_texts(sub_body))
                elif sub == "Student-Facing Targets":
                    prep.student_targets = [b.text for b in sub_body if b.kind == "li"]
        elif heading == "Required Materials":
            for sub, sub_body in _sections(body, "h4"):
                items = [b.text for b in sub_body if b.kind == "li"]
                if sub and items:
                    prep.materials.append((sub, items))
        elif heading == "Required Preparation":
            for sub, sub_body in _sections(body, "h3"):
                if sub == "":
                    prep.required_prep = _texts(sub_body)
                elif sub == "Standards Alignment":
                    prep.standards = _standards(sub_body)
        elif heading == "Glossary":
            for term, term_body in _sections(body, "h3")[1:]:
                definition = next((b.text for b in term_body if b.kind == "p"), "")
                prep.glossary.append((term, definition))
    if not prep.standards:
        for heading, body in _sections(blocks, "h3"):
            if heading == "Standards Alignment":
                prep.standards = _standards(body)
    return prep


# ---------------------------------------------------------------------------
# Lesson page
# ---------------------------------------------------------------------------

_ACTIVITY_NUMBER = re.compile(r"^\d+\.\d+$")
_MINUTES = re.compile(r"^(\d+)\s*mins?$")


@dataclass
class Activity:
    number: str
    kind: str  # Warm-up, Activity, ...
    minutes: int | None
    title: str
    routines: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    standards: dict[str, list[str]] = field(default_factory=dict)
    narrative: list[str] = field(default_factory=list)
    launch: list[str] = field(default_factory=list)
    task: list[str] = field(default_factory=list)
    student_thinking: list[str] = field(default_factory=list)
    extension: list[str] = field(default_factory=list)
    synthesis: list[str] = field(default_factory=list)
    marked_optional: bool = False  # the site prints an "Optional" subtitle under the heading

    @property
    def optional(self) -> bool:
        return self.marked_optional or "optional" in self.kind.lower()


@dataclass
class Lesson:
    label: str = ""  # "Unit 1, Lesson 2"
    title: str = ""
    activities: list[Activity] = field(default_factory=list)
    lesson_synthesis: list[str] = field(default_factory=list)
    cooldown: list[str] = field(default_factory=list)
    cooldown_minutes: int | None = None
    summary: list[str] = field(default_factory=list)


_CARD_FIELDS = {
    "Activity Narrative": "narrative",
    "Launch": "launch",
    "Student Task Statement": "task",
    "Building on Student Thinking": "student_thinking",
    "Are You Ready for More?": "extension",
    "Activity Synthesis": "synthesis",
}


def _parse_activity(number: str, kind: str, body: list[Block]) -> Activity:
    minutes = None
    title = ""
    head: list[Block] = []
    rest = body
    for i, b in enumerate(body):
        if minutes is None and (m := _MINUTES.match(b.text)):
            minutes = int(m.group(1))
            continue
        if b.kind == "h3":
            title = b.text
            rest = body[i + 1 :]
            break
        head.append(b)
    act = Activity(number=number, kind=kind, minutes=minutes, title=title,
                   marked_optional=any(b.text == "Optional" for b in head))

    # Everything before the first known h3 card is the metadata area (h4 boxes).
    meta: list[Block] = []
    cards: list[tuple[str, list[Block]]] = []
    for heading, blocks in _sections(rest, "h3"):
        if heading == "":
            meta = blocks
        else:
            cards.append((heading, blocks))
    for heading, blocks in _sections(meta, "h4"):
        if heading == "Instructional Routines":
            act.routines = [b.text for b in blocks if b.kind == "p" and b.text[:1].isupper()]
        elif heading == "Materials":
            act.materials = [b.text for b in blocks if b.kind == "p" and not b.text.startswith("To ")]
            labels = [b.text for b in blocks if b.kind == "p" and b.text.startswith("To ")]
            if labels and act.materials:
                act.materials = _label_materials(blocks)
        elif heading == "Standards Alignment":
            act.standards = _standards(blocks)
    for heading, blocks in cards:
        attr = _CARD_FIELDS.get(heading)
        if attr:
            setattr(act, attr, _to_lines(blocks))
    if minutes is None:
        for b in head:
            if m := _MINUTES.match(b.text):
                act.minutes = int(m.group(1))
    return act


def _label_materials(blocks: list[Block]) -> list[str]:
    """Materials under "To Gather" / "To Copy (...)" become "Item (to copy ...)"."""
    out, label = [], ""
    for b in blocks:
        if b.kind != "p":
            continue
        if b.text.startswith("To "):
            label = re.sub(r"[()]", "", b.text[3:]).lower()
        else:
            out.append(f"{b.text} ({label})" if label else b.text)
    return out


def parse_lesson(html: str) -> Lesson:
    blocks = flatten(html)
    lesson = Lesson()
    i = 0
    while i < len(blocks) and blocks[i].kind != "h1":
        if re.match(r"^Unit \d+, Lesson \d+$", blocks[i].text):
            lesson.label = blocks[i].text
        i += 1
    if i < len(blocks):
        lesson.title = blocks[i].text
    blocks = blocks[i + 1 :]

    # Activities are introduced by a bare "N.M" paragraph followed by an h2.
    chunks: list[tuple[str, str, list[Block]]] = []
    pending_number = ""
    for i, b in enumerate(blocks):
        next_is_heading = i + 1 < len(blocks) and blocks[i + 1].kind == "h2"
        if b.kind == "p" and _ACTIVITY_NUMBER.match(b.text) and next_is_heading:
            pending_number = b.text
            continue
        if b.kind == "h2":
            chunks.append((pending_number, b.text, []))
            pending_number = ""
            continue
        if chunks:
            chunks[-1][2].append(b)

    for number, heading, body in chunks:
        low = heading.lower()
        if number:
            lesson.activities.append(_parse_activity(number, heading, body))
        elif low == "lesson synthesis":
            lesson.lesson_synthesis = _to_lines(body)
        elif low.startswith("cool-down") or low.startswith("cool down"):
            cd = _parse_activity("", heading, body)
            lesson.cooldown = cd.task or _to_lines(body)
            lesson.cooldown_minutes = cd.minutes
        elif low == "student lesson summary":
            lesson.summary = _to_lines(body)
    return lesson


# ---------------------------------------------------------------------------
# Practice page
# ---------------------------------------------------------------------------


@dataclass
class Problem:
    number: int
    review_of: int | None  # earlier lesson number for spiral-review problems
    task: list[str] = field(default_factory=list)


def parse_practice(html: str) -> list[Problem]:
    """Practice problems from a lesson's public Practice page, in order."""
    problems: list[Problem] = []
    for heading, body in _sections(flatten(html), "h2"):
        if heading.endswith("Resources"):
            break
        m = re.fullmatch(r"Problem (\d+)", heading)
        if not m:
            continue
        review = next((re.match(r"^For\s*Lesson\s*(\d+)", b.text) for b in body
                       if re.match(r"^For\s*Lesson", b.text)), None)
        task_blocks = [b for b in body if b.kind != "h3" and not re.match(r"^For\s*Lesson", b.text)]
        problems.append(Problem(int(m.group(1)), int(review.group(1)) if review else None, _to_lines(task_blocks)))
    return problems
