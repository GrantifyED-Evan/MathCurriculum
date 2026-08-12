"""Turn human course references into the site's family/course numbering.

The IM site addresses courses as /{family}/{audience}/{course}/... where family is
MS or HS and course is a bare integer. Teachers think in terms of "Grade 8" or
"Algebra 1", so everything user-facing accepts those names instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

AUDIENCES = ("teachers", "students")


@dataclass(frozen=True)
class Course:
    slug: str          # canonical short key, e.g. "grade8" / "alg1"
    name: str          # display name, e.g. "Grade 8"
    family: str        # "MS" or "HS"
    number: int        # course number in the URL

    @property
    def path(self) -> str:
        return f"/{self.family}/teachers/{self.number}/index.html"


COURSES: tuple[Course, ...] = (
    Course("grade6", "Grade 6", "MS", 1),
    Course("grade7", "Grade 7", "MS", 2),
    Course("grade8", "Grade 8", "MS", 3),
    Course("alg1", "Algebra 1", "HS", 1),
    Course("geometry", "Geometry", "HS", 2),
    Course("alg2", "Algebra 2", "HS", 3),
    Course("alg1supports", "Algebra 1 Supports", "HS", 4),
)

# Everything a person might reasonably type, mapped to a canonical slug.
_ALIASES: dict[str, str] = {
    "6": "grade6", "g6": "grade6", "grade6": "grade6", "6th": "grade6",
    "7": "grade7", "g7": "grade7", "grade7": "grade7", "7th": "grade7",
    "8": "grade8", "g8": "grade8", "grade8": "grade8", "8th": "grade8",
    "alg1": "alg1", "algebra1": "alg1", "a1": "alg1",
    "geo": "geometry", "geometry": "geometry",
    "alg2": "alg2", "algebra2": "alg2", "a2": "alg2",
    "alg1supports": "alg1supports", "algebra1supports": "alg1supports",
    "supports": "alg1supports", "alg1s": "alg1supports",
}

_BY_SLUG = {course.slug: course for course in COURSES}


def _normalize(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def resolve_course(token: str) -> Course:
    """Resolve "8", "Grade 8", "alg1", "Algebra 1", or "HS/2" to a Course."""
    raw = token.strip()

    # Direct family/number form, e.g. "MS/3" or "HS-2".
    family_match = re.fullmatch(r"(MS|HS)[/\-_ ]?(\d+)", raw, re.IGNORECASE)
    if family_match:
        family = family_match.group(1).upper()
        number = int(family_match.group(2))
        for course in COURSES:
            if course.family == family and course.number == number:
                return course
        raise ValueError(f"No course numbered {number} in family {family}")

    key = _normalize(raw)
    if key in _ALIASES:
        return _BY_SLUG[_ALIASES[key]]

    raise ValueError(
        f"Unrecognized course {token!r}. Known courses: "
        + ", ".join(f"{c.name} ({c.slug})" for c in COURSES)
    )


@dataclass(frozen=True)
class LessonRef:
    course: Course
    unit: int
    lesson: int | None = None

    def path(self, audience: str = "teachers", page: str = "index.html") -> str:
        parts = [self.course.family, audience, str(self.course.number), str(self.unit)]
        if self.lesson is not None:
            parts.append(str(self.lesson))
        return "/" + "/".join(parts) + "/" + page

    def label(self) -> str:
        if self.lesson is None:
            return f"{self.course.name} Unit {self.unit}"
        return f"{self.course.name} Unit {self.unit} Lesson {self.lesson}"


def _clean_tokens(text: str) -> list[str]:
    """Split a reference into tokens, dropping filler words like "Unit"/"Lesson".

    "u3"/"l5" shorthand is unwrapped to the bare number so that
    "Grade 8 U1 L2" parses the same as "8.1.2".
    """
    tokens: list[str] = []
    for raw in re.split(r"[.\s/\-_]+", text.strip()):
        if not raw:
            continue
        lowered = raw.lower()
        if lowered in ("unit", "lesson", "course"):
            continue
        shorthand = re.fullmatch(r"([ul])(\d+)", lowered)
        tokens.append(shorthand.group(2) if shorthand else raw)
    return tokens


def parse_ref(text: str) -> LessonRef:
    """Parse a lesson or unit reference into a LessonRef.

    Accepts "8.1.2", "grade8 1 2", "Grade 8.1.2", "Algebra 1 Unit 2 Lesson 4",
    "alg1.3", and "MS/3/1/2". A reference with no lesson component addresses the
    whole unit.
    """
    tokens = _clean_tokens(text)
    if not tokens:
        raise ValueError("Empty reference")

    # "MS/3/1/2" — the family and its number are two separate tokens.
    if tokens[0].upper() in ("MS", "HS") and len(tokens) >= 2:
        candidates = [(resolve_course(f"{tokens[0]}/{tokens[1]}"), tokens[2:])]
    else:
        # Course names can be several words ("Algebra 1 Supports"), so try the
        # longest prefix that resolves and leaves a usable unit/lesson tail.
        candidates = []
        for size in range(min(3, len(tokens)), 0, -1):
            try:
                course = resolve_course(" ".join(tokens[:size]))
            except ValueError:
                continue
            candidates.append((course, tokens[size:]))

        if not candidates:
            raise ValueError(
                f"Unrecognized course in {text!r}. Known courses: "
                + ", ".join(f"{c.name} ({c.slug})" for c in COURSES)
            )

    # Prefer an interpretation whose remainder is one or two plain numbers.
    for course, rest in candidates:
        if 1 <= len(rest) <= 2 and all(part.isdigit() for part in rest):
            return LessonRef(
                course=course,
                unit=int(rest[0]),
                lesson=int(rest[1]) if len(rest) > 1 else None,
            )

    course, rest = candidates[0]
    if not rest:
        raise ValueError(
            f"Reference {text!r} names {course.name} but no unit. Use e.g. '8.1' or '8.1.2'."
        )
    raise ValueError(
        f"Could not read a unit and lesson from {text!r}; expected numbers after "
        f"{course.name}."
    )
