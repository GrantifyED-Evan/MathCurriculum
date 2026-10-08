"""Courses on accessim.org, lesson references, and unit/lesson listings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from . import fetch as fetch_mod
from . import parse


@dataclass(frozen=True)
class Course:
    slug: str
    name: str
    path: str
    aliases: tuple[str, ...] = ()


COURSES = [
    Course("grade6", "Grade 6", "/6-8/grade-6", ("6", "g6", "6th")),
    Course("grade7", "Grade 7", "/6-8/grade-7", ("7", "g7", "7th")),
    Course("grade8", "Grade 8", "/6-8/grade-8", ("8", "g8", "8th")),
    Course("acc6", "Accelerated 6", "/6-8-accelerated/accelerated-6", ("accelerated6",)),
    Course("acc7", "Accelerated 7", "/6-8-accelerated/accelerated-7", ("accelerated7",)),
    Course("alg1", "Algebra 1", "/9-12-aga/algebra-1", ("algebra1", "a1")),
    Course("geometry", "Geometry", "/9-12-aga/geometry", ("geo",)),
    Course("alg2", "Algebra 2", "/9-12-aga/algebra-2", ("algebra2", "a2")),
]


def resolve_course(token: str) -> Course:
    key = re.sub(r"[\s_-]", "", token.lower())
    for course in COURSES:
        if key in {course.slug, re.sub(r"\s", "", course.name.lower()), *course.aliases}:
            return course
    raise ValueError(f"Unknown course {token!r}. Try one of: {', '.join(c.slug for c in COURSES)}")


@dataclass(frozen=True)
class Ref:
    course: Course
    unit: int
    lesson: int | None = None

    def __str__(self) -> str:
        short = self.course.slug.removeprefix("grade")
        return f"{short}.{self.unit}" + (f".{self.lesson}" if self.lesson else "")


def parse_ref(text: str) -> Ref:
    """Parse "8.1.2", "grade8.1.2", "alg1.2.4" or "8.1" (unit only)."""
    m = re.fullmatch(r"\s*([A-Za-z0-9 _-]*?)[.\s](\d+)(?:[.\s](\d+))?\s*", text)
    if not m:
        raise ValueError(f"Could not read reference {text!r}; expected e.g. 8.1.2 or alg1.2.4")
    return Ref(resolve_course(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None)


def units(course: Course, *, refresh: bool = False) -> list[dict]:
    html = parse.resolve_stream(fetch_mod.fetch(course.path, refresh=refresh))
    found: dict[int, dict] = {}
    for m in re.finditer(rf'href="{re.escape(course.path)}/unit-(\d+)\?', html):
        found.setdefault(int(m.group(1)), {"number": int(m.group(1))})
    titles = {}
    blocks = parse.flatten(fetch_mod.fetch(course.path))
    for i, b in enumerate(blocks):
        if b.kind == "h2" and (u := re.fullmatch(r"Unit (\d+)", b.text)):
            if i + 1 < len(blocks) and blocks[i + 1].kind == "h3":
                titles[int(u.group(1))] = blocks[i + 1].text
    for n, unit in found.items():
        unit["title"] = titles.get(n, "")
        unit["path"] = f"{course.path}/unit-{n}"
    return [found[k] for k in sorted(found)]


@lru_cache(maxsize=64)
def unit_info(course: Course, unit: int, *, refresh: bool = False) -> dict:
    path = f"{course.path}/unit-{unit}"
    html = fetch_mod.fetch(path, refresh=refresh)
    return {"number": unit, "path": path, "title": parse.unit_title(html), "lessons": parse.unit_lessons(html)}

