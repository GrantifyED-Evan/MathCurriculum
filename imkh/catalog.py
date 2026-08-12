"""Build and query the curriculum catalog: courses -> units -> lessons.

The catalog is a small JSON file that lets the agent answer structural questions
("which unit covers exponents?") without refetching anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import http, parse
from .refs import COURSES, Course, resolve_course


def catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "catalog.json"


def build_course(course: Course, *, refresh: bool = False) -> dict[str, Any]:
    """Crawl one course's index and unit pages into a catalog entry."""
    index_html = http.fetch(course.path, refresh=refresh)
    units = parse.parse_course_index(index_html, course.family, course.number)

    unit_entries = []
    for unit in units:
        unit_path = f"/{course.family}/teachers/{course.number}/{unit.number}/index.html"
        unit_html = http.fetch(unit_path, refresh=refresh, allow_missing=True)
        lessons = (
            parse.parse_unit_index(unit_html, course.family, course.number, unit.number)
            if unit_html
            else []
        )
        unit_entries.append(
            {
                "number": unit.number,
                "title": unit.title,
                "sections": unit.sections,
                "path": unit_path,
                "lessons": [
                    {
                        "number": lesson.number,
                        "title": lesson.title,
                        "section": lesson.section,
                        "ref": f"{course.slug}.{unit.number}.{lesson.number}",
                    }
                    for lesson in lessons
                ],
            }
        )

    return {
        "slug": course.slug,
        "name": course.name,
        "family": course.family,
        "number": course.number,
        "path": course.path,
        "units": unit_entries,
    }


def build(course_tokens: list[str] | None = None, *, refresh: bool = False) -> dict[str, Any]:
    """Build (or rebuild) the catalog for the given courses, merging with any existing one."""
    selected = (
        [resolve_course(token) for token in course_tokens] if course_tokens else list(COURSES)
    )

    existing = load(required=False) or {"courses": {}}
    catalog: dict[str, Any] = {"courses": dict(existing.get("courses", {}))}

    for course in selected:
        catalog["courses"][course.slug] = build_course(course, refresh=refresh)

    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    return catalog


def load(*, required: bool = True) -> dict[str, Any] | None:
    path = catalog_path()
    if not path.exists():
        if required:
            raise FileNotFoundError(
                "No catalog yet. Run:  python3 -m imkh build"
            )
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_course(catalog: dict[str, Any], token: str) -> dict[str, Any]:
    course = resolve_course(token)
    entry = catalog.get("courses", {}).get(course.slug)
    if not entry:
        raise KeyError(
            f"{course.name} is not in the catalog yet. Run:  python3 -m imkh build {course.slug}"
        )
    return entry


def get_unit(catalog: dict[str, Any], token: str, unit_number: int) -> dict[str, Any]:
    course_entry = get_course(catalog, token)
    for unit in course_entry["units"]:
        if unit["number"] == unit_number:
            return unit
    raise KeyError(f"{course_entry['name']} has no unit {unit_number}")


def iter_lessons(catalog: dict[str, Any]):
    """Yield (course_entry, unit_entry, lesson_entry) across the whole catalog."""
    for course_entry in catalog.get("courses", {}).values():
        for unit in course_entry["units"]:
            for lesson in unit["lessons"]:
                yield course_entry, unit, lesson
