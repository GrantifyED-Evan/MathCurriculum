"""Search the catalog by title and, when lessons have been synced, by full text."""

from __future__ import annotations

import re
from typing import Any

from . import http, parse
from .refs import resolve_course


def _tokenize(query: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 1]


def search_titles(
    catalog: dict[str, Any], query: str, *, course: str | None = None, limit: int = 25
) -> list[dict[str, Any]]:
    """Rank lessons and units by how well their titles match the query."""
    tokens = _tokenize(query)
    if not tokens:
        return []

    course_slug = resolve_course(course).slug if course else None
    hits: list[dict[str, Any]] = []

    for course_entry in catalog.get("courses", {}).values():
        if course_slug and course_entry["slug"] != course_slug:
            continue
        for unit in course_entry["units"]:
            for lesson in unit["lessons"]:
                haystack = f"{lesson['title']} {lesson['section']} {unit['title']}".lower()
                score = sum(3 for token in tokens if token in lesson["title"].lower())
                score += sum(1 for token in tokens if token in haystack)
                if score:
                    hits.append(
                        {
                            "ref": lesson["ref"],
                            "course": course_entry["name"],
                            "unit": unit["number"],
                            "unit_title": unit["title"],
                            "lesson": lesson["number"],
                            "title": lesson["title"],
                            "section": lesson["section"],
                            "score": score,
                        }
                    )

    hits.sort(key=lambda hit: (-hit["score"], hit["course"], hit["unit"], hit["lesson"]))
    return hits[:limit]


def search_fulltext(
    catalog: dict[str, Any],
    query: str,
    *,
    course: str | None = None,
    limit: int = 15,
    context_chars: int = 260,
) -> list[dict[str, Any]]:
    """Search the text of lessons already in the cache.

    Only cached pages are searched — this never triggers a crawl. Run
    `python3 -m imkh sync` first to make a course fully searchable.
    """
    tokens = _tokenize(query)
    if not tokens:
        return []

    course_slug = resolve_course(course).slug if course else None
    phrase = re.compile(re.escape(query.strip()), re.IGNORECASE)
    hits: list[dict[str, Any]] = []

    for course_entry in catalog.get("courses", {}).values():
        if course_slug and course_entry["slug"] != course_slug:
            continue
        for unit in course_entry["units"]:
            for lesson in unit["lessons"]:
                path = (
                    f"/{course_entry['family']}/teachers/{course_entry['number']}"
                    f"/{unit['number']}/{lesson['number']}/index.html"
                )
                if not http.is_cached(path):
                    continue

                text = parse.to_markdown(parse.extract_main(http.fetch(path)))
                lowered = text.lower()
                score = sum(lowered.count(token) for token in tokens)
                if not score:
                    continue

                phrase_match = phrase.search(text)
                if phrase_match:
                    score += 25
                    center = phrase_match.start()
                else:
                    first = min(
                        (lowered.find(token) for token in tokens if lowered.find(token) >= 0),
                        default=0,
                    )
                    center = first

                start = max(0, center - context_chars // 2)
                snippet = re.sub(r"\s+", " ", text[start: start + context_chars]).strip()

                hits.append(
                    {
                        "ref": lesson["ref"],
                        "course": course_entry["name"],
                        "unit": unit["number"],
                        "lesson": lesson["number"],
                        "title": lesson["title"],
                        "score": score,
                        "snippet": ("…" if start else "") + snippet + "…",
                    }
                )

    hits.sort(key=lambda hit: -hit["score"])
    return hits[:limit]
