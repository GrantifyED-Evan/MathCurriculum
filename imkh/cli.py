"""Command-line interface: python3 -m imkh <command> ..."""

from __future__ import annotations

import argparse
import json
import sys

from . import catalog as catalog_mod
from . import http, render, search
from .refs import COURSES, resolve_course, parse_ref


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_courses(args: argparse.Namespace) -> int:
    existing = catalog_mod.load(required=False) or {"courses": {}}
    rows = []
    for course in COURSES:
        entry = existing["courses"].get(course.slug)
        rows.append(
            {
                "slug": course.slug,
                "name": course.name,
                "family": course.family,
                "units": len(entry["units"]) if entry else None,
                "in_catalog": entry is not None,
            }
        )

    if args.json:
        _print_json(rows)
        return 0

    print(f"{'REF':<14}{'COURSE':<22}{'UNITS':<8}CATALOG")
    for row in rows:
        units = str(row["units"]) if row["units"] is not None else "-"
        print(
            f"{row['slug']:<14}{row['name']:<22}{units:<8}"
            f"{'yes' if row['in_catalog'] else 'not built'}"
        )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    tokens = args.courses or None
    print(
        "Building catalog for: "
        + (", ".join(resolve_course(t).name for t in tokens) if tokens else "all courses"),
        file=sys.stderr,
    )
    catalog = catalog_mod.build(tokens, refresh=args.refresh)

    total_units = total_lessons = 0
    for entry in catalog["courses"].values():
        total_units += len(entry["units"])
        total_lessons += sum(len(unit["lessons"]) for unit in entry["units"])

    print(
        f"Catalog written to {catalog_mod.catalog_path()}: "
        f"{len(catalog['courses'])} courses, {total_units} units, {total_lessons} lessons",
        file=sys.stderr,
    )
    return 0


def cmd_units(args: argparse.Namespace) -> int:
    catalog = catalog_mod.load()
    entry = catalog_mod.get_course(catalog, args.course)

    if args.json:
        _print_json(entry["units"])
        return 0

    print(f"{entry['name']} — {len(entry['units'])} units\n")
    for unit in entry["units"]:
        print(f"  Unit {unit['number']}: {unit['title']}  ({len(unit['lessons'])} lessons)")
        for section in unit["sections"]:
            print(f"      · {section}")
    return 0


def cmd_lessons(args: argparse.Namespace) -> int:
    catalog = catalog_mod.load()
    unit = catalog_mod.get_unit(catalog, args.course, args.unit)
    course_entry = catalog_mod.get_course(catalog, args.course)

    if args.json:
        _print_json(unit["lessons"])
        return 0

    print(f"{course_entry['name']} Unit {unit['number']}: {unit['title']}\n")
    current_section = None
    for lesson in unit["lessons"]:
        if lesson["section"] != current_section:
            current_section = lesson["section"]
            if current_section:
                print(f"  [{current_section}]")
        print(f"    {lesson['ref']:<18}Lesson {lesson['number']}: {lesson['title']}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    ref = parse_ref(args.ref)

    if ref.lesson is None or args.page in ("assessments.html", "resources.html"):
        result = render.unit_markdown(
            ref, audience=args.audience, page=args.page, refresh=args.refresh
        )
    else:
        result = render.lesson_markdown(
            ref, audience=args.audience, page=args.page, refresh=args.refresh
        )

    if args.json:
        _print_json(result)
    else:
        print(render.as_document(result))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    catalog = catalog_mod.load()
    query = " ".join(args.query)

    if args.fulltext:
        hits = search.search_fulltext(
            catalog, query, course=args.course, limit=args.limit
        )
    else:
        hits = search.search_titles(catalog, query, course=args.course, limit=args.limit)

    if args.json:
        _print_json(hits)
        return 0

    if not hits:
        hint = (
            "  (no cached lesson text yet — run 'python3 -m imkh sync <course>' first)"
            if args.fulltext
            else ""
        )
        print(f"No matches for {query!r}.{hint}")
        return 1

    for hit in hits:
        print(f"{hit['ref']:<20}{hit['course']} U{hit['unit']} L{hit['lesson']}: {hit['title']}")
        if hit.get("snippet"):
            print(f"    {hit['snippet']}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Download every lesson page for a course so full-text search works offline."""
    catalog = catalog_mod.load()
    entries = (
        [catalog_mod.get_course(catalog, token) for token in args.courses]
        if args.courses
        else list(catalog["courses"].values())
    )

    fetched = skipped = failed = 0
    for entry in entries:
        for unit in entry["units"]:
            for lesson in unit["lessons"]:
                path = (
                    f"/{entry['family']}/{args.audience}/{entry['number']}"
                    f"/{unit['number']}/{lesson['number']}/index.html"
                )
                if http.is_cached(path) and not args.refresh:
                    skipped += 1
                    continue
                try:
                    http.fetch(path, refresh=args.refresh)
                    fetched += 1
                    print(
                        f"  fetched {entry['name']} U{unit['number']} L{lesson['number']}: "
                        f"{lesson['title']}",
                        file=sys.stderr,
                    )
                except http.FetchError as exc:
                    failed += 1
                    print(f"  FAILED {path}: {exc}", file=sys.stderr)

    print(
        f"Sync complete: {fetched} fetched, {skipped} already cached, {failed} failed.",
        file=sys.stderr,
    )
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m imkh",
        description=(
            "Read the public Illustrative Mathematics curriculum hosted by Kendall Hunt. "
            "References look like '8.1.2' (Grade 8, Unit 1, Lesson 2) or 'alg1.3.5'."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_json(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--json", action="store_true", help="emit JSON instead of text")

    p_courses = subparsers.add_parser("courses", help="list available courses")
    add_json(p_courses)
    p_courses.set_defaults(func=cmd_courses)

    p_build = subparsers.add_parser("build", help="build the course/unit/lesson catalog")
    p_build.add_argument("courses", nargs="*", help="courses to build (default: all)")
    p_build.add_argument("--refresh", action="store_true", help="bypass the page cache")
    p_build.set_defaults(func=cmd_build)

    p_units = subparsers.add_parser("units", help="list units in a course")
    p_units.add_argument("course")
    add_json(p_units)
    p_units.set_defaults(func=cmd_units)

    p_lessons = subparsers.add_parser("lessons", help="list lessons in a unit")
    p_lessons.add_argument("course")
    p_lessons.add_argument("unit", type=int)
    add_json(p_lessons)
    p_lessons.set_defaults(func=cmd_lessons)

    p_get = subparsers.add_parser("get", help="print a lesson or unit as Markdown")
    p_get.add_argument("ref", help="e.g. 8.1.2, alg1.3.5, or 8.1 for a unit overview")
    p_get.add_argument(
        "--audience", choices=["teachers", "students"], default="teachers"
    )
    p_get.add_argument(
        "--page",
        default="index.html",
        choices=[
            "index.html",
            "preparation.html",
            "practice.html",
            "assessments.html",
            "resources.html",
        ],
        help="which page of the lesson/unit to read",
    )
    p_get.add_argument("--refresh", action="store_true", help="bypass the page cache")
    add_json(p_get)
    p_get.set_defaults(func=cmd_get)

    p_search = subparsers.add_parser("search", help="search lesson titles or full text")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--course", help="restrict to one course, e.g. grade8")
    p_search.add_argument(
        "--fulltext",
        action="store_true",
        help="search cached lesson bodies instead of titles (needs 'sync')",
    )
    p_search.add_argument("--limit", type=int, default=25)
    add_json(p_search)
    p_search.set_defaults(func=cmd_search)

    p_sync = subparsers.add_parser(
        "sync", help="cache every lesson page in a course for offline full-text search"
    )
    p_sync.add_argument("courses", nargs="*", help="courses to sync (default: all in catalog)")
    p_sync.add_argument("--audience", choices=["teachers", "students"], default="teachers")
    p_sync.add_argument("--refresh", action="store_true")
    p_sync.set_defaults(func=cmd_sync)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except http.FetchError as exc:
        print(f"fetch error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
