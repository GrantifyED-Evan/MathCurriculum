"""Build an in-class plan for one lesson.

The plan is a minute-by-minute run of show built from the lesson's own
structure: warm-up, activities, lesson synthesis, and cool-down. For each block
it pulls out what a teacher needs at the front of the room — grouping, launch
steps, the student task, what to watch for, the discussion questions to ask, and
access supports — and checks the total against the class period.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import courses, fetch, parse

# Lesson pages do not print synthesis or cool-down durations. The course guide
# ("An IM Lesson") says the synthesis takes 5-10 minutes and the cool-down about
# 5, so plans use the low end and mark those times as suggested.
#
# Default schedule: 50-minute blocks with 40-48 minutes of productive
# (instructional) time; the rest goes to entry, transitions, and dismissal.
DEFAULT_PERIOD = 50
DEFAULT_WORK_MIN = 40
DEFAULT_WORK_MAX = 48
SYNTHESIS_MINUTES = 5
COOLDOWN_MINUTES = 5

_SUPPORT_PREFIXES = (
    "Engagement:",
    "Representation:",
    "Action and Expression:",
    "Supports accessibility for:",
    "Advances:",
    "Access for",
    "MLR",
)
_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}


@dataclass
class Segment:
    start: int
    end: int
    minutes: int
    label: str  # "Warm-up 2.1", "Activity 2.2", "Lesson Synthesis", "Cool-down"
    title: str = ""
    grouping: str = ""
    routines: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    optional: bool = False
    suggested_time: bool = False
    purpose: str = ""
    launch: list[str] = field(default_factory=list)
    task: list[str] = field(default_factory=list)
    monitor: list[str] = field(default_factory=list)
    student_thinking: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    synthesis: list[str] = field(default_factory=list)
    supports: list[str] = field(default_factory=list)
    extension: list[str] = field(default_factory=list)


@dataclass
class LessonPlan:
    ref: str
    course: str
    unit: int
    unit_title: str
    lesson: int
    title: str
    source_url: str
    prep_url: str
    period: int
    work_min: int
    work_max: int
    student_goal: str = ""
    learning_goals: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    standards: dict[str, list[str]] = field(default_factory=dict)
    vocabulary: list[tuple[str, str]] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    prep_notes: list[str] = field(default_factory=list)
    narrative: list[str] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    total: int = 0
    timing_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?:(?<=[.!?])|(?<=[.!?]”))\s+(?=[A-Z“])", text) if s.strip()]


def grouping(launch: list[str]) -> str:
    text = " ".join(launch)
    m = re.search(r"groups of (\d+|two|three|four|five)(?:[–-](\d+))?", text, re.I)
    if m:
        size = _WORDS.get(m.group(1).lower(), m.group(1))
        if str(size) == "2" and not m.group(2):
            return "Partners"
        return f"Groups of {size}" + (f"–{m.group(2)}" if m.group(2) else "")
    if re.search(r"\b(partners?|pairs?)\b", text, re.I):
        return "Partners"
    if re.search(r"same groups", text, re.I):
        return "Same groups"
    if re.search(r"\b(individually|independent(ly)?|quiet work time|quiet think time)\b", text, re.I):
        return "Individual, then share"
    if re.search(r"whole[- ]class|whole group", text, re.I):
        return "Whole class"
    return ""


def purpose(narrative: list[str]) -> str:
    for para in narrative:
        for s in _sentences(para):
            if re.search(r"\b(purpose|goal) of this\b", s, re.I):
                return s
    return _sentences(narrative[0])[0] if narrative else ""


def monitor_for(narrative: list[str]) -> list[str]:
    return [
        s
        for para in narrative
        for s in _sentences(para)
        if re.search(r"\b(monitor|look for|listen for|select (students|groups))", s, re.I)
    ]


def questions(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        for q in re.findall(r"[“\"]([^”\"]*?\?[^”\"]*?)[”\"]", line):
            q = " ".join(q.split())
            if q not in found:
                found.append(q)
    return found


def split_supports(lines: list[str]) -> tuple[list[str], list[str]]:
    steps, supports = [], []
    for line in lines:
        bare = line.lstrip("• ")
        (supports if bare.startswith(_SUPPORT_PREFIXES) else steps).append(line)
    return steps, supports


# ---------------------------------------------------------------------------
# Plan assembly
# ---------------------------------------------------------------------------


def build(lesson: parse.Lesson, prep: parse.Preparation, *, ref: courses.Ref, unit_title: str,
          source_path: str, period: int = DEFAULT_PERIOD, work_min: int = DEFAULT_WORK_MIN,
          work_max: int = DEFAULT_WORK_MAX) -> LessonPlan:
    plan = LessonPlan(
        ref=str(ref),
        course=ref.course.name,
        unit=ref.unit,
        unit_title=unit_title,
        lesson=ref.lesson or 0,
        title=lesson.title or prep.title,
        source_url=fetch.url_for(source_path),
        prep_url=fetch.url_for(source_path + "/preparation"),
        period=period,
        work_min=min(work_min, work_max, period),
        work_max=min(work_max, period),
        student_goal=prep.student_goal,
        learning_goals=prep.learning_goals,
        targets=prep.student_targets,
        standards=prep.standards,
        vocabulary=prep.glossary,
        prep_notes=prep.required_prep,
        narrative=prep.narrative,
        summary=lesson.summary,
    )

    materials: list[str] = []
    for act in lesson.activities:
        for item in act.materials:
            if item not in materials:
                materials.append(item)
    for _, items in prep.materials:
        for item in items:
            if not any(m.startswith(item) for m in materials):
                materials.append(item)
    plan.materials = materials

    clock = 0
    for act in lesson.activities:
        minutes = act.minutes or 0
        launch, launch_supports = split_supports(act.launch)
        synthesis, synth_supports = split_supports(act.synthesis)
        seg = Segment(
            start=clock,
            end=clock + minutes,
            minutes=minutes,
            label=f"{act.kind} {act.number}",
            title=act.title,
            grouping=grouping(act.launch),
            routines=act.routines,
            materials=act.materials,
            optional=act.optional,
            suggested_time=act.minutes is None,
            purpose=purpose(act.narrative),
            launch=launch,
            task=act.task,
            monitor=monitor_for(act.narrative),
            student_thinking=act.student_thinking,
            questions=questions(act.launch + act.synthesis),
            synthesis=synthesis,
            supports=launch_supports + synth_supports,
            extension=act.extension,
        )
        plan.segments.append(seg)
        clock += minutes

    if lesson.lesson_synthesis:
        steps, supports = split_supports(lesson.lesson_synthesis)
        plan.segments.append(
            Segment(
                start=clock,
                end=clock + SYNTHESIS_MINUTES,
                minutes=SYNTHESIS_MINUTES,
                label="Lesson Synthesis",
                grouping="Whole class",
                suggested_time=True,
                purpose=purpose(lesson.lesson_synthesis),
                questions=questions(lesson.lesson_synthesis),
                synthesis=steps,
                supports=supports,
            )
        )
        clock += SYNTHESIS_MINUTES

    cd_minutes = lesson.cooldown_minutes or COOLDOWN_MINUTES
    plan.segments.append(
        Segment(
            start=clock,
            end=clock + cd_minutes,
            minutes=cd_minutes,
            label="Cool-down",
            grouping="Individual",
            suggested_time=lesson.cooldown_minutes is None,
            purpose="Quick formative check of today's learning goal; collect and sort to plan tomorrow.",
            task=lesson.cooldown,
        )
    )
    clock += cd_minutes
    plan.total = clock
    plan.timing_notes = _timing_notes(plan)
    return plan


def _timing_notes(plan: LessonPlan) -> list[str]:
    notes = []
    window = f"{plan.work_min}–{plan.work_max} productive min of a {plan.period}-min block"
    if plan.total > plan.work_max:
        need = plan.total - plan.work_max
        notes.append(f"Planned time is {plan.total} min: {need} min over the {window}. Cut at least {need} min:")
        options = [(f"Skip optional {s.label}", s.minutes) for s in plan.segments if s.optional]
        warm = next((s for s in plan.segments if s.label.lower().startswith("warm")), None)
        if warm and warm.minutes > 5:
            options.append(("Trim the warm-up to 5 min", warm.minutes - 5))
        cooldown = next((s for s in plan.segments if s.label == "Cool-down"), None)
        if cooldown:
            options.append(("Give the cool-down at the start of the next class", cooldown.minutes))
        saved = 0
        for text, minutes in options:
            saved += minutes
            notes.append(f"{text} (saves {minutes}; {saved} total).")
        if saved < need:
            notes.append(f"Still {need - saved} min over: split the lesson across two days.")
    elif plan.total < plan.work_min:
        short = plan.work_min - plan.total
        notes.append(f"Planned time is {plan.total} min: {short} min under the {window}. Add at least {short} min:")
        if any(s.label == "Lesson Synthesis" for s in plan.segments):
            notes.append("Extend the lesson synthesis to 10 min (IM range 5–10; adds 5).")
        if any(s.extension for s in plan.segments):
            notes.append("Use the “Are you ready for more?” extensions.")
        notes.append("Start the practice problems in class.")
    else:
        notes.append(
            f"Planned time is {plan.total} min: within the {window}, "
            f"leaving {plan.period - plan.total} min for entry, transitions, and dismissal."
        )
    if any(s.suggested_time for s in plan.segments):
        notes.append("Times marked * are suggested (IM course guide: synthesis 5–10 min, cool-down about 5 min).")
    return notes


def make(ref_text: str, *, period: int = DEFAULT_PERIOD, work_min: int = DEFAULT_WORK_MIN,
         work_max: int = DEFAULT_WORK_MAX, refresh: bool = False) -> LessonPlan:
    ref = courses.parse_ref(ref_text)
    if ref.lesson is None:
        raise ValueError(f"{ref_text!r} names a unit; give a lesson, e.g. {ref}.1")
    info = courses.unit_info(ref.course, ref.unit, refresh=refresh)
    match = next((l for l in info["lessons"] if l["number"] == ref.lesson), None)
    if not match:
        raise ValueError(f"{ref.course.name} Unit {ref.unit} has no Lesson {ref.lesson}")
    lesson = parse.parse_lesson(fetch.fetch(match["path"], refresh=refresh))
    prep = parse.parse_preparation(fetch.fetch(match["path"] + "/preparation", refresh=refresh))
    return build(lesson, prep, ref=ref, unit_title=info["title"], source_path=match["path"],
                 period=period, work_min=work_min, work_max=work_max)
