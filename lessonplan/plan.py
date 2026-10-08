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

# Block structure (the teacher's routine), in order:
#   Opener            5 min   the lesson's warm-up (its task is the first task
#                             statement of the lesson), timeboxed
#   Lesson            the lesson's required activities at their listed times,
#                     shortened (longest first, never below 5 min) only when
#                     needed to leave room for MIN_CYCLES practice cycles
#   Practice cycles   5 min each: students do one problem alone, then the
#                     teacher goes over it; as many as fit
#   Closing synthesis 5-10 min, always last (IM course guide: synthesis 5-10)
#
# Default schedule: one 50-minute block with 40-50 minutes of productive time.
DEFAULT_PERIOD = 50
DEFAULT_WORK_MIN = 40
DEFAULT_WORK_MAX = 50
OPENER_MINUTES = 5
CLOSING_MINUTES = 5
CLOSING_MAX_MINUTES = 10
CYCLE_MINUTES = 5
MIN_CYCLES = 2
MIN_ACTIVITY_MINUTES = 5

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
    adjustment: str = ""  # how the planner changed this block to fit the window
    listed_minutes: int | None = None  # the time the curriculum lists, if any


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
    practice_url: str
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
    unused_practice: list[str] = field(default_factory=list)
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


def _activity_segment(act: parse.Activity, label: str) -> Segment:
    launch, launch_supports = split_supports(act.launch)
    synthesis, synth_supports = split_supports(act.synthesis)
    return Segment(
        start=0, end=0, minutes=act.minutes or 0, listed_minutes=act.minutes,
        label=label, title=act.title,
        grouping=grouping(act.launch), routines=act.routines, materials=act.materials,
        optional=act.optional, suggested_time=act.minutes is None,
        purpose=purpose(act.narrative), launch=launch, task=act.task,
        monitor=monitor_for(act.narrative), student_thinking=act.student_thinking,
        questions=questions(act.launch + act.synthesis), synthesis=synthesis,
        supports=launch_supports + synth_supports, extension=act.extension,
    )


def _opener(lesson: parse.Lesson) -> Segment | None:
    warm = next((a for a in lesson.activities if a.kind.lower().startswith("warm")), None)
    if warm:
        seg = _activity_segment(warm, f"Opener ({warm.kind} {warm.number})")
    else:
        # No warm-up: open with the first problem of the first activity's task.
        first = next((a for a in lesson.activities if a.task and not a.optional), None)
        if not first:
            return None
        seg = Segment(start=0, end=0, minutes=0, label=f"Opener (from Activity {first.number})",
                      title=first.title, grouping="Individual, then share",
                      purpose="Open with the first problem of the lesson's first task statement.",
                      task=first.task[:3])
    if seg.minutes != OPENER_MINUTES:
        if seg.listed_minutes:
            seg.adjustment = f"Timeboxed to {OPENER_MINUTES} min (curriculum lists {seg.listed_minutes})."
        seg.minutes = OPENER_MINUTES
    seg.suggested_time = False
    return seg


def _closing(lesson: parse.Lesson, prep: parse.Preparation) -> Segment:
    seg = Segment(start=0, end=0, minutes=CLOSING_MINUTES, label="Closing Synthesis", grouping="Whole class")
    if lesson.lesson_synthesis:
        steps, supports = split_supports(lesson.lesson_synthesis)
        seg.purpose = purpose(lesson.lesson_synthesis)
        seg.questions = questions(lesson.lesson_synthesis)
        seg.synthesis, seg.supports = steps, supports
    else:
        # The lesson has no Lesson Synthesis; build one from its targets and summary.
        seg.purpose = "Pull the lesson together before students leave."
        seg.questions = [f"How do you know: {t[0].lower() + t[1:]}" if t.startswith("I ") else t
                         for t in prep.student_targets]
        seg.synthesis = (["Ask students to share how today's work connects to the goal: " + prep.student_goal]
                         if prep.student_goal else []) + [f"Key idea: {l.lstrip('• ')}" for l in lesson.summary[:3]]
        seg.adjustment = "This lesson has no Lesson Synthesis; closing built from its student targets and summary."
    return seg


def _practice_segment(n: int, problem: parse.Problem, practice_url: str) -> Segment:
    review = f" (review of Lesson {problem.review_of})" if problem.review_of else ""
    return Segment(
        start=0, end=0, minutes=CYCLE_MINUTES, label=f"Practice {n}", title=f"Problem {problem.number}{review}",
        grouping="Individual, then teacher goes over it",
        purpose="Students do this problem on their own, then go over it together.",
        task=problem.task,
        synthesis=[f"Go over Problem {problem.number}. Answer keys need an accessim.org sign-in; "
                   f"problem source: {practice_url}"],
    )


def build(lesson: parse.Lesson, prep: parse.Preparation, *, ref: courses.Ref, unit_title: str,
          source_path: str, problems: list[parse.Problem] | None = None, period: int = DEFAULT_PERIOD,
          work_min: int = DEFAULT_WORK_MIN, work_max: int = DEFAULT_WORK_MAX) -> LessonPlan:
    plan = LessonPlan(
        ref=str(ref), course=ref.course.name, unit=ref.unit, unit_title=unit_title, lesson=ref.lesson or 0,
        title=lesson.title or prep.title,
        source_url=fetch.url_for(source_path),
        prep_url=fetch.url_for(source_path + "/preparation"),
        practice_url=fetch.url_for(source_path + "/practice"),
        period=period, work_min=min(work_min, work_max, period), work_max=min(work_max, period),
        student_goal=prep.student_goal, learning_goals=prep.learning_goals, targets=prep.student_targets,
        standards=prep.standards, vocabulary=prep.glossary, prep_notes=prep.required_prep,
        narrative=prep.narrative, summary=lesson.summary,
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

    lo, hi = plan.work_min, plan.work_max
    opener = _opener(lesson)
    closing = _closing(lesson, prep)
    activities = [_activity_segment(a, f"{a.kind} {a.number}") for a in lesson.activities
                  if not a.kind.lower().startswith("warm")]
    required = [a for a in activities if not a.optional]
    optional = [a for a in activities if a.optional]
    problems = list(problems or [])
    # Current-lesson problems first, then spiral review.
    ordered = [p for p in problems if p.review_of is None] + [p for p in problems if p.review_of is not None]

    fixed = (opener.minutes if opener else 0) + closing.minutes
    want_cycles = min(len(ordered), MIN_CYCLES)

    def planned() -> int:
        return fixed + sum(a.minutes for a in required) + want_cycles * CYCLE_MINUTES

    # Bring in optional activities only when required work cannot reach the minimum.
    for seg in optional:
        if planned() >= lo:
            break
        if planned() + seg.minutes <= hi:
            seg.optional = False
            seg.adjustment = "Optional activity included to fill the block."
            required.append(seg)
    required.sort(key=activities.index)

    # Shorten activities (longest first) if needed to leave room for practice.
    budget = hi - fixed - want_cycles * CYCLE_MINUTES
    while sum(a.minutes for a in required) > budget:
        longest = max(required, key=lambda a: a.minutes, default=None)
        if not longest or longest.minutes <= MIN_ACTIVITY_MINUTES:
            break
        cut = min(sum(a.minutes for a in required) - budget, longest.minutes - MIN_ACTIVITY_MINUTES)
        longest.minutes -= cut
        longest.adjustment = (f"Shortened from {longest.listed_minutes} to {longest.minutes} min "
                              "to make room for practice.")

    used = fixed + sum(a.minutes for a in required)
    cycles = max(0, min(len(ordered), (hi - used) // CYCLE_MINUTES))
    practice = [_practice_segment(i + 1, p, plan.practice_url) for i, p in enumerate(ordered[:cycles])]
    plan.unused_practice = [f"Problem {p.number}" + (f" (review of Lesson {p.review_of})" if p.review_of else "")
                            for p in ordered[cycles:]]
    used += cycles * CYCLE_MINUTES

    # Leftover minutes go to the closing synthesis, up to IM's 10-minute upper bound.
    extra = min(CLOSING_MAX_MINUTES - closing.minutes, hi - used)
    if extra > 0:
        closing.minutes += extra
        note = f"Lengthened to {closing.minutes} min to use the remaining time."
        closing.adjustment = (closing.adjustment + " " + note).strip()

    plan.segments = ([opener] if opener else []) + required + practice + [closing] + [a for a in activities if a.optional]
    _retime(plan)
    plan.timing_notes = _timing_notes(plan, lesson)
    return plan


def _retime(plan: LessonPlan) -> None:
    clock = 0
    for seg in plan.segments:
        seg.start = clock
        if not seg.optional:
            clock += seg.minutes
        seg.end = clock
    plan.total = clock


def _timing_notes(plan: LessonPlan, lesson: parse.Lesson) -> list[str]:
    notes = []
    window = f"{plan.work_min}–{plan.work_max} productive min of a {plan.period}-min block"
    if plan.work_min <= plan.total <= plan.work_max:
        notes.append(f"Planned time is {plan.total} min: within the {window}, "
                     f"leaving {plan.period - plan.total} min for entry, transitions, and dismissal.")
    else:
        notes.append(f"Planned time is {plan.total} min: outside the {window}.")
    cycles = sum(1 for s in plan.segments if s.label.startswith("Practice "))
    notes.append(f"Practice: {cycles} cycle(s) of {CYCLE_MINUTES} min (one problem alone, then go over it)."
                 if cycles else "Practice: this lesson has no practice problems on accessim.org.")
    if plan.unused_practice:
        notes.append("Not scheduled (assign as homework or use if time): " + ", ".join(plan.unused_practice) + ".")
    notes += [f"{s.label}: {s.adjustment}" for s in plan.segments if s.adjustment]
    for seg in (s for s in plan.segments if s.optional):
        notes.append(f"Optional {seg.label} ({seg.minutes} min) is not scheduled.")
    notes.append("The IM cool-down is not scheduled; the closing synthesis ends the block.")
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
    try:
        problems = parse.parse_practice(fetch.fetch(match["path"] + "/practice", refresh=refresh))
    except fetch.NotFound:
        problems = []
    return build(lesson, prep, ref=ref, unit_title=info["title"], source_path=match["path"],
                 problems=problems, period=period, work_min=work_min, work_max=work_max)
