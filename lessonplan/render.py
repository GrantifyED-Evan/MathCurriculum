"""Render a LessonPlan as Markdown or as a printable HTML page."""

from __future__ import annotations

import html

from .plan import LessonPlan, Segment

ATTRIBUTION = (
    "Source: IM 6–8 Math v.360 / IM 9–12 Math, © Illustrative Mathematics, "
    "licensed CC BY-NC 4.0 (accessim.org). Plan generated from the public teacher view."
)


def _time(seg: Segment) -> str:
    return f"{seg.minutes} min" + ("*" if seg.suggested_time else "")


def _md_time(seg: Segment) -> str:
    return _time(seg).replace("*", "\\*")


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _md_list(items: list[str]) -> list[str]:
    return [f"- {i.lstrip('• ')}" for i in items]


def markdown(plan: LessonPlan) -> str:
    out = [
        f"# {plan.course} · Unit {plan.unit} · Lesson {plan.lesson}: {plan.title}",
        "",
        f"*Unit {plan.unit}: {plan.unit_title}* · Reference `{plan.ref}` · "
        f"[Lesson]({plan.source_url}) · [Preparation]({plan.prep_url})",
        "",
    ]
    if plan.student_goal:
        out += [f"**Student goal (post on board):** {plan.student_goal}", ""]
    if plan.learning_goals:
        out += ["## Learning goals", *_md_list(plan.learning_goals), ""]
    if plan.targets:
        out += ["## Student targets", *_md_list(plan.targets), ""]
    if plan.standards:
        out += ["## Standards"]
        out += [f"- **{k}:** {', '.join(v)}" for k, v in plan.standards.items()]
        out += [""]

    out += ["## Before class"]
    out += _md_list([f"☐ {m}" for m in plan.materials]) or ["- No special materials listed."]
    out += _md_list(plan.prep_notes)
    out += [""]
    if plan.vocabulary:
        out += ["## Vocabulary"]
        out += [f"- **{t}** — {d}" for t, d in plan.vocabulary]
        out += [""]

    out += [
        f"## Agenda ({plan.total} of {plan.period} min)",
        "",
        "| Time | Block | Title | Grouping | Routines |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in plan.segments:
        label = s.label + (" (optional)" if s.optional else "")
        out.append(
            f"| {s.start}–{s.end} ({_md_time(s)}) | {label} | {s.title} | {s.grouping} | {', '.join(s.routines)} |"
        )
    out += [""]
    out += [f"> {n}" for n in plan.timing_notes]
    out += [""]

    for s in plan.segments:
        out += [f"## {s.start}–{s.end} min · {s.label}" + (f": {s.title}" if s.title else "")]
        meta = [p for p in (_md_time(s), s.grouping, ", ".join(s.routines)) if p]
        out += [f"*{' · '.join(meta)}*", ""]
        if s.purpose:
            out += [f"**Purpose:** {s.purpose}", ""]
        sections = [
            ("Launch", s.launch),
            ("Students do", s.task),
            ("Monitor for", s.monitor),
            ("If students struggle", s.student_thinking),
            ("Ask", [f"“{q}”" for q in s.questions]),
            ("Synthesis", s.synthesis),
            ("Access supports", s.supports),
            ("Are you ready for more?", s.extension),
        ]
        if s.label == "Cool-down" and not s.task:
            sections.append(("Note", ["Cool-down text requires an accessim.org sign-in; use the printed or Blackline Master copy."]))
        for heading, items in sections:
            if items:
                out += [f"**{heading}**", *_md_list(items), ""]
    if plan.summary:
        out += ["## Student lesson summary", *_md_list(plan.summary), ""]
    out += ["## Teacher notes", "", "_ _", "", "---", f"*{ATTRIBUTION}*", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS = """
:root{--bg:#fff;--fg:#1d1f23;--muted:#5d6470;--line:#d9dde3;--accent:#1f5fa8;--chip:#eef3fa;--warn:#8a4b00;--warnbg:#fff4e0}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e8eaed;--muted:#a0a7b2;--line:#2e333a;--accent:#7fb0ef;--chip:#1f2a38;--warn:#ffcf8a;--warnbg:#2f2615}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:900px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}
h1{font-size:1.6rem;margin:.2em 0}
h2{font-size:1.2rem;margin:1.6em 0 .4em;border-bottom:1px solid var(--line);padding-bottom:.2em}
h3{font-size:1rem;margin:1em 0 .2em}
.sub{color:var(--muted)}
.goal{background:var(--chip);border-radius:8px;padding:10px 14px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.95rem}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.note{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:8px 12px;margin:.6em 0}
.seg{border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:14px 0;break-inside:avoid}
.seg h2{border:0;margin:0}
.meta{color:var(--muted);font-size:.9rem}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 10px;margin:2px 4px 2px 0;font-size:.85rem}
ul{margin:.2em 0 .6em;padding-left:1.3em}
.nav{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.notes{min-height:120px;border:1px dashed var(--line);border-radius:8px}
form.inline{display:inline-flex;gap:6px;align-items:center}
input,select,button{font:inherit}
footer{color:var(--muted);font-size:.8rem;margin-top:32px}
@media print{.nav,form{display:none}.seg{border-color:#999}body{font-size:12px}main{padding:0}.page{break-after:page}}
"""


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_e(i.lstrip('• '))}</li>" for i in items) + "</ul>" if items else ""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title><style>{CSS}</style></head><body><main>{body}"
        f"<footer>{_e(ATTRIBUTION)}</footer></main></body></html>"
    )


def html_fragment(plan: LessonPlan) -> str:
    h = [
        f"<div class='page'><div class='sub'>{_e(plan.course)} · Unit {plan.unit}: {_e(plan.unit_title)}</div>",
        f"<h1>Lesson {plan.lesson}: {_e(plan.title)}</h1>",
        f"<div class='sub'><code>{_e(plan.ref)}</code> · <a href='{_e(plan.source_url)}'>Lesson</a> · "
        f"<a href='{_e(plan.prep_url)}'>Preparation</a></div>",
    ]
    if plan.student_goal:
        h.append(f"<p class='goal'>{_e(plan.student_goal)}</p>")
    if plan.learning_goals:
        h.append("<h3>Learning goals</h3>" + _ul(plan.learning_goals))
    if plan.targets:
        h.append("<h3>Student targets</h3>" + _ul(plan.targets))
    if plan.standards:
        h.append("<h3>Standards</h3>" + _ul([f"{k}: {', '.join(v)}" for k, v in plan.standards.items()]))
    h.append("<h2>Before class</h2>")
    h.append(_ul([f"☐ {m}" for m in plan.materials] + plan.prep_notes) or "<p>No special materials listed.</p>")
    if plan.vocabulary:
        h.append("<h2>Vocabulary</h2><ul>" + "".join(
            f"<li><b>{_e(t)}</b> — {_e(d)}</li>" for t, d in plan.vocabulary) + "</ul>")

    h.append(f"<h2>Agenda · {plan.total} of {plan.period} min</h2><table><tr><th>Time</th><th>Block</th>"
             "<th>Title</th><th>Grouping</th><th>Routines</th></tr>")
    for s in plan.segments:
        label = s.label + (" (optional)" if s.optional else "")
        h.append(f"<tr><td>{s.start}–{s.end}<br><span class='meta'>{_time(s)}</span></td><td>{_e(label)}</td>"
                 f"<td>{_e(s.title)}</td><td>{_e(s.grouping)}</td><td>{_e(', '.join(s.routines))}</td></tr>")
    h.append("</table>")
    h += [f"<div class='note'>{_e(n)}</div>" for n in plan.timing_notes]

    for s in plan.segments:
        h.append("<section class='seg'>")
        h.append(f"<h2>{s.start}–{s.end} min · {_e(s.label)}{': ' + _e(s.title) if s.title else ''}</h2>")
        chips = [_time(s)] + ([s.grouping] if s.grouping else []) + s.routines + (["optional"] if s.optional else [])
        h.append("<div>" + "".join(f"<span class='chip'>{_e(c)}</span>" for c in chips) + "</div>")
        if s.purpose:
            h.append(f"<p><b>Purpose:</b> {_e(s.purpose)}</p>")
        for heading, items in (
            ("Launch", s.launch),
            ("Students do", s.task),
            ("Monitor for", s.monitor),
            ("If students struggle", s.student_thinking),
            ("Ask", [f"“{q}”" for q in s.questions]),
            ("Synthesis", s.synthesis),
            ("Access supports", s.supports),
            ("Are you ready for more?", s.extension),
        ):
            if items:
                h.append(f"<h3>{heading}</h3>{_ul(items)}")
        if s.label == "Cool-down" and not s.task:
            h.append("<p class='meta'>Cool-down text requires an accessim.org sign-in; use the printed or "
                     "Blackline Master copy.</p>")
        h.append("</section>")
    if plan.summary:
        h.append("<h2>Student lesson summary</h2>" + _ul(plan.summary))
    h.append("<h2>Teacher notes</h2><div class='notes'></div></div>")
    return "".join(h)


def html_page(plan: LessonPlan) -> str:
    return page(f"{plan.ref} {plan.title}", html_fragment(plan))
