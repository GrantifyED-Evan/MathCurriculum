---
name: kendall-hunt
description: >-
  Look up Illustrative Mathematics curriculum material published by Kendall Hunt
  (im.kendallhunt.com) — Grades 6-8, Algebra 1, Geometry, Algebra 2, Algebra 1
  Supports. Use when the user asks about IM or Kendall Hunt lessons, units,
  warm-ups, activities, cool-downs, practice problems, standards alignment,
  pacing, or lesson planning, or names a lesson reference like "8.1.2" or
  "Algebra 1 Unit 2 Lesson 4".
---

# Kendall Hunt / Illustrative Mathematics curriculum

Read curriculum from the public IM site through the local `imkh` toolkit. Run
everything from the repository root; it uses only the Python standard library.

## Quick start

```bash
python3 -m imkh courses                 # what's available
python3 -m imkh search pythagorean      # find lessons by title
python3 -m imkh units grade8            # units in a course
python3 -m imkh lessons grade8 1        # lessons in a unit
python3 -m imkh get 8.1.2               # read a lesson
```

If a command reports that the catalog is missing or a course is not built:

```bash
python3 -m imkh build            # all courses, ~1 minute
python3 -m imkh build grade8     # or just one
```

## References

`course.unit.lesson` — `8.1.2`, `alg1.3.5`. Omit the lesson for the unit
overview (`8.1`). Course tokens are forgiving: `8`, `grade8`, `Grade 8`, and
`MS/3` all work.

| Slug | Course |
| --- | --- |
| `grade6` `grade7` `grade8` | Grades 6, 7, 8 |
| `alg1` | Algebra 1 |
| `geometry` | Geometry |
| `alg2` | Algebra 2 |
| `alg1supports` | Algebra 1 Supports |

## Choosing the right page

`get` defaults to the lesson body. Use `--page` for the rest:

```bash
python3 -m imkh get 8.1.2 --page preparation.html   # goals, standards, materials
python3 -m imkh get 8.1.2 --page practice.html      # practice problems
python3 -m imkh get 8.1   --page assessments.html   # unit assessments
python3 -m imkh get 8.1.2 --audience students       # student-facing version
```

For "help me plan this lesson", read `preparation.html` **and** `index.html` —
the first has the learning goals and standards, the second has the activities
and timings.

## Searching

Title search works immediately and covers every catalogued lesson. Full-text
search covers only lessons already downloaded:

```bash
python3 -m imkh search "scientific notation" --course grade8
python3 -m imkh sync grade8                     # cache the course (a few minutes)
python3 -m imkh search "number talk" --fulltext --course grade8
```

If `--fulltext` returns nothing, say the course has not been synced rather than
concluding the content does not exist.

## What is not available

- **Student Responses (answer keys) are gated on every lesson** — they need a
  free Kendall Hunt teacher registration this toolkit does not have. Output
  marks them `_[Gated: ...]_`. Say so directly instead of inferring answers and
  presenting them as IM's.
- K–5 is not published on this site.
- Diagrams come through as image URLs with alt text, not viewable images.

Never try to log in or work around a gate.

## Citing

Every `get` result includes its source URL. Pass the reference and URL along so
the teacher can open the original.
