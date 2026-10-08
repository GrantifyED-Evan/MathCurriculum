"""Command line: python3 -m lessonplan <command> ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import courses, plan, render


def _write(p: plan.LessonPlan, out: Path, fmt: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    name = f"{p.ref}-{''.join(c if c.isalnum() else '-' for c in p.title.lower()).strip('-')}"
    while "--" in name:
        name = name.replace("--", "-")
    path = out / f"{name}.{'md' if fmt == 'md' else 'html'}"
    path.write_text(render.markdown(p) if fmt == "md" else render.html_page(p), encoding="utf-8")
    return path


def cmd_plan(args) -> int:
    p = plan.make(args.ref, period=args.period, refresh=args.refresh)
    if args.out:
        print(_write(p, Path(args.out), args.format))
    else:
        print(render.markdown(p) if args.format == "md" else render.html_page(p))
    return 0


def _batch(refs: list[str], args) -> int:
    failures = 0
    for ref in refs:
        try:
            path = _write(plan.make(ref, period=args.period, refresh=args.refresh), Path(args.out), args.format)
            print(path)
        except Exception as exc:  # keep going; report at the end
            failures += 1
            print(f"FAILED {ref}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def _unit_refs(course: courses.Course, unit: int) -> list[str]:
    short = course.slug.removeprefix("grade")
    return [f"{short}.{unit}.{l['number']}" for l in courses.unit_info(course, unit)["lessons"]]


def cmd_unit(args) -> int:
    ref = courses.parse_ref(args.unit)
    return _batch(_unit_refs(ref.course, ref.unit), args)


def cmd_course(args) -> int:
    course = courses.resolve_course(args.course)
    refs = [r for u in courses.units(course) for r in _unit_refs(course, u["number"])]
    return _batch(refs, args)


def cmd_list(args) -> int:
    if args.target is None:
        for c in courses.COURSES:
            print(f"{c.slug:<10}{c.name}")
        return 0
    try:
        ref = courses.parse_ref(args.target)
    except ValueError:
        course = courses.resolve_course(args.target)
        for u in courses.units(course):
            print(f"Unit {u['number']}: {u['title']}")
        return 0
    info = courses.unit_info(ref.course, ref.unit)
    print(f"Unit {ref.unit}: {info['title']}")
    short = ref.course.slug.removeprefix("grade")
    for l in info["lessons"]:
        print(f"  {short}.{ref.unit}.{l['number']:<4}{l['title']}")
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    serve(args.host, args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lessonplan", description="Build in-class plans for IM lessons (accessim.org).")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--period", type=int, default=plan.DEFAULT_PERIOD, help="class period in minutes (default 45)")
        p.add_argument("--format", choices=["md", "html"], default="md")
        p.add_argument("--refresh", action="store_true", help="re-download instead of using the cache")

    p = sub.add_parser("plan", help="plan one lesson, e.g. 8.1.2")
    p.add_argument("ref")
    p.add_argument("--out", help="write to this directory instead of stdout")
    common(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("unit", help="plan every lesson in a unit, e.g. 8.1")
    p.add_argument("unit")
    p.add_argument("--out", default="plans")
    common(p)
    p.set_defaults(func=cmd_unit)

    p = sub.add_parser("course", help="plan every lesson in a course, e.g. grade8")
    p.add_argument("course")
    p.add_argument("--out", default="plans")
    common(p)
    p.set_defaults(func=cmd_course)

    p = sub.add_parser("list", help="list courses, units (grade8) or lessons (8.1)")
    p.add_argument("target", nargs="?")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("serve", help="run the web app")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
