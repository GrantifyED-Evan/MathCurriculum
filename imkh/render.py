"""Fetch a lesson or unit and render it as Markdown for reading in context."""

from __future__ import annotations

from typing import Any

from . import BASE_URL, http, parse
from .refs import LessonRef

# Pages that exist alongside a lesson's main page.
LESSON_PAGES = ("index.html", "preparation.html")
UNIT_PAGES = ("index.html", "assessments.html", "resources.html")


def lesson_markdown(
    ref: LessonRef,
    *,
    audience: str = "teachers",
    page: str = "index.html",
    refresh: bool = False,
) -> dict[str, Any]:
    """Fetch one lesson page and return its title, body Markdown, and source URL."""
    if ref.lesson is None:
        raise ValueError(f"{ref.label()} is a unit reference; use unit_markdown instead")

    path = ref.path(audience=audience, page=page)
    page_html = http.fetch(path, refresh=refresh)
    parsed = parse.parse_lesson(page_html)

    return {
        "ref": f"{ref.course.slug}.{ref.unit}.{ref.lesson}",
        "label": ref.label(),
        "audience": audience,
        "page": page,
        "title": parsed["title"],
        "markdown": parsed["markdown"],
        "url": f"{BASE_URL}{path}",
    }


def unit_markdown(
    ref: LessonRef,
    *,
    audience: str = "teachers",
    page: str = "index.html",
    refresh: bool = False,
) -> dict[str, Any]:
    """Fetch a unit-level page (overview, assessments, or resources)."""
    unit_ref = LessonRef(course=ref.course, unit=ref.unit, lesson=None)
    path = unit_ref.path(audience=audience, page=page)
    page_html = http.fetch(path, refresh=refresh)
    main = parse.extract_main(page_html)

    return {
        "ref": f"{ref.course.slug}.{ref.unit}",
        "label": unit_ref.label(),
        "audience": audience,
        "page": page,
        "markdown": parse.to_markdown(main),
        "url": f"{BASE_URL}{path}",
    }


def as_document(result: dict[str, Any]) -> str:
    """Render a fetch result as a self-contained Markdown document with provenance."""
    header = [f"# {result['label']}"]
    if result.get("title") and result["title"] != result["label"]:
        header.append(f"**{result['title']}**")
    header.append(f"Source: {result['url']}")
    header.append(f"Audience: {result['audience']} · Page: {result['page']}")
    return "\n\n".join(header) + "\n\n---\n\n" + result["markdown"] + "\n"
