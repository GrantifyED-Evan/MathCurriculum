"""Local web app: browse a course, open any lesson's in-class plan, print a unit.

    python3 -m lessonplan serve            # http://localhost:8000
"""

from __future__ import annotations

import html
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import courses, plan, render

e = html.escape


def _period(query: dict) -> int:
    try:
        return max(20, min(120, int(query.get("period", [plan.DEFAULT_PERIOD])[0])))
    except ValueError:
        return plan.DEFAULT_PERIOD


def _period_form(action: str, period: int) -> str:
    return (
        f"<form class='inline' method='get' action='{e(action)}'>Class period "
        f"<input type='number' name='period' min='20' max='120' value='{period}' style='width:5em'> min "
        "<button>Update</button></form>"
    )


def home(_: dict) -> str:
    rows = "".join(
        f"<li><a href='/c/{c.slug}'>{e(c.name)}</a></li>" for c in courses.COURSES
    )
    body = (
        "<h1>In-Class Lesson Planner</h1>"
        "<p class='sub'>Choose a course, then a unit, then a lesson to get a minute-by-minute plan "
        "built from the IM curriculum on accessim.org.</p>"
        f"<ul>{rows}</ul>"
        "<form class='inline' method='get' action='/plan'>Jump to lesson "
        "<input name='ref' placeholder='8.1.2' style='width:7em'> <button>Open</button></form>"
    )
    return render.page("In-Class Lesson Planner", body)


def course_page(slug: str, _: dict) -> str:
    course = courses.resolve_course(slug)
    rows = "".join(
        f"<li><a href='/c/{course.slug}/{u['number']}'>Unit {u['number']}</a> — {e(u['title'])}</li>"
        for u in courses.units(course)
    )
    body = f"<div class='nav'><a href='/'>All courses</a></div><h1>{e(course.name)}</h1><ul>{rows}</ul>"
    return render.page(course.name, body)


def unit_page(slug: str, unit: int, query: dict) -> str:
    course = courses.resolve_course(slug)
    info = courses.unit_info(course, unit)
    period = _period(query)
    short = course.slug.removeprefix("grade")
    rows = "".join(
        f"<tr><td>{l['number']}</td><td><a href='/plan/{short}.{unit}.{l['number']}?period={period}'>"
        f"{e(l['title'])}</a></td><td class='meta'>{e(l['goal'])}</td></tr>"
        for l in info["lessons"]
    )
    body = (
        f"<div class='nav'><a href='/'>All courses</a><a href='/c/{course.slug}'>{e(course.name)}</a></div>"
        f"<h1>Unit {unit}: {e(info['title'])}</h1>"
        f"<p>{_period_form(f'/c/{course.slug}/{unit}', period)} · "
        f"<a href='/c/{course.slug}/{unit}/all?period={period}'>All plans for this unit (print)</a></p>"
        f"<table><tr><th>#</th><th>Lesson</th><th>Student goal</th></tr>{rows}</table>"
    )
    return render.page(f"{course.name} Unit {unit}", body)


def unit_all_page(slug: str, unit: int, query: dict) -> str:
    course = courses.resolve_course(slug)
    info = courses.unit_info(course, unit)
    period = _period(query)
    short = course.slug.removeprefix("grade")
    parts = [
        f"<div class='nav'><a href='/c/{course.slug}/{unit}?period={period}'>Back to unit</a>"
        "<a href='javascript:window.print()'>Print</a></div>"
    ]
    for lesson in info["lessons"]:
        p = plan.make(f"{short}.{unit}.{lesson['number']}", period=period)
        parts.append(render.html_fragment(p))
    return render.page(f"{course.name} Unit {unit} plans", "".join(parts))


def plan_page(ref_text: str, query: dict) -> str:
    period = _period(query)
    p = plan.make(ref_text, period=period)
    ref = courses.parse_ref(ref_text)
    nav = (
        f"<div class='nav'><a href='/'>All courses</a><a href='/c/{ref.course.slug}'>{e(ref.course.name)}</a>"
        f"<a href='/c/{ref.course.slug}/{ref.unit}?period={period}'>Unit {ref.unit}</a>"
        f"<a href='/plan/{e(p.ref)}.md?period={period}'>Download Markdown</a>"
        "<a href='javascript:window.print()'>Print</a></div>"
        f"<p>{_period_form(f'/plan/{p.ref}', period)}</p>"
    )
    return render.page(f"{p.ref} {p.title}", nav + render.html_fragment(p))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        parts = [urllib.parse.unquote(p) for p in url.path.strip("/").split("/") if p]
        try:
            if not parts:
                self._send(home(query))
            elif parts == ["plan"] and "ref" in query:
                self.send_response(302)
                self.send_header("Location", f"/plan/{query['ref'][0].strip()}")
                self.end_headers()
            elif parts[0] == "plan" and len(parts) == 2 and parts[1].endswith(".md"):
                p = plan.make(parts[1][:-3], period=_period(query))
                self._send(render.markdown(p), "text/markdown; charset=utf-8",
                           {"Content-Disposition": f"attachment; filename=\"{p.ref}.md\""})
            elif parts[0] == "plan" and len(parts) == 2:
                self._send(plan_page(parts[1], query))
            elif parts[0] == "c" and len(parts) == 2:
                self._send(course_page(parts[1], query))
            elif parts[0] == "c" and len(parts) == 3:
                self._send(unit_page(parts[1], int(parts[2]), query))
            elif parts[0] == "c" and len(parts) == 4 and parts[3] == "all":
                self._send(unit_all_page(parts[1], int(parts[2]), query))
            else:
                self._send(render.page("Not found", "<h1>Not found</h1><a href='/'>Home</a>"), status=404)
        except ValueError as exc:
            self._send(render.page("Not found", f"<h1>Not found</h1><p>{e(str(exc))}</p><a href='/'>Home</a>"), status=404)
        except Exception as exc:  # show the error rather than a blank page
            traceback.print_exc()
            self._send(render.page("Error", f"<h1>Error</h1><pre>{e(repr(exc))}</pre>"), status=500)

    def _send(self, body: str, ctype: str = "text/html; charset=utf-8", headers: dict | None = None, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Lesson planner running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
