# In-class lesson planner

`lessonplan/` builds a minute-by-minute **in-class plan for every lesson** of the
IM curriculum on [accessim.org](https://accessim.org/6-8/grade-8?a=teacher)
(Grades 6–8, Accelerated 6–7, Algebra 1, Geometry, Algebra 2). Python 3.10+
standard library only.

Each plan has:

- Student goal, learning goals, student targets, standards
- Before-class checklist: materials, copies, required preparation
- Vocabulary for the lesson
- Agenda table with start/end minutes, grouping, and instructional routines
- Per block (warm-up, activities, lesson synthesis, cool-down): purpose, launch
  steps, student task, what to monitor for, responses to student struggles,
  discussion questions, synthesis moves, access supports
- Every lesson fit to one block (default: 50 min with 40–50 min of productive
  time), in this order:
  1. **Opener** (5 min): the lesson's warm-up, timeboxed.
  2. **Lesson**: the required activities at their listed times. The longest are
     shortened (never below 5 min) only when needed to leave two practice cycles.
  3. **Practice cycles** (5 min each): students do one problem from the lesson's
     practice problems alone, then the teacher goes over it. Current-lesson
     problems come first, then review problems; as many cycles as fit.
  4. **Closing synthesis** (5–10 min): always last. Uses the lesson's synthesis,
     or one built from its student targets when the lesson has none.
  Optional activities are scheduled only when a lesson is otherwise too short.
  Every change from the curriculum's listed times is labeled "Adjusted".
- Links back to the source lesson and preparation pages

### Web app

```bash
python3 -m lessonplan serve        # open http://127.0.0.1:8000
```

Pick a course → unit → lesson. Set the block length and productive-time range, print a plan,
download it as Markdown, or open "All plans for this unit" to print a unit.

### Command line

```bash
python3 -m lessonplan list grade8                       # units
python3 -m lessonplan list 8.1                          # lessons in a unit
python3 -m lessonplan plan 8.1.2                        # one plan to stdout
python3 -m lessonplan plan 8.1.2 --format html --out plans
python3 -m lessonplan plan 8.1.2 --period 55 --work-min 45 --work-max 55  # other schedules
python3 -m lessonplan unit 8.1 --out plans/grade8       # every lesson in a unit
python3 -m lessonplan course grade8 --out plans/grade8  # every lesson in a course
```

Ready-made plans for Grade 8 Unit 1 (17 lessons) are in `plans/grade8/unit-1/`, including one printable HTML file with all 17.

### Limits

- Cool-down text, student responses, and assessments need an accessim.org
  sign-in; plans note this instead of fetching them.
- accessim.org does not print durations for the lesson synthesis or cool-down;
  plans use 5 min each and mark them with `*`.
- Diagrams appear as their alt text.
- Content is © Illustrative Mathematics, CC BY-NC 4.0; every plan carries that
  attribution.

# Kendall Hunt curriculum agent

A Claude Code agent, plus the toolkit behind it, for reading the
[Illustrative Mathematics curriculum published by Kendall Hunt](https://im.kendallhunt.com).

Ask in plain language — "what's in Grade 8 Unit 3?", "pull the cool-down for
7.2.5", "which lessons cover the Pythagorean theorem?", "help me plan Algebra 1
Unit 2 Lesson 4" — and the agent finds the right lesson, fetches it, and answers
with a citation back to the source page.

## What it covers

| Reference | Course | Units |
| --- | --- | --- |
| `grade6` | Grade 6 | 9 |
| `grade7` | Grade 7 | 9 |
| `grade8` | Grade 8 | 9 |
| `alg1` | Algebra 1 | 7 |
| `geometry` | Geometry | 8 |
| `alg2` | Algebra 2 | 7 |
| `alg1supports` | Algebra 1 Supports | 7 |

927 lessons in total. For each lesson the agent can read the lesson itself
(warm-up, activities, launches, syntheses, cool-down), the preparation page
(narrative, learning goals, standards, required materials), the practice
problems, and the student-facing version. Unit-level assessment and resource
pages are available too.

## Setup

Nothing to install — Python 3.10+ standard library only.

```bash
python3 -m imkh build     # build the catalog for all courses (~1 minute)
```

The catalog is committed, so this is only needed to refresh it.

## Using it from Claude Code

Just ask. The `kendall-hunt` agent in `.claude/agents/` and the matching skill
in `.claude/skills/` trigger on curriculum questions:

> Which Grade 8 lessons introduce the Pythagorean theorem, and what's the
> warm-up for the first one?

> Give me the learning goals and required materials for alg1.2.4.

## Using the toolkit directly

```bash
python3 -m imkh courses                      # list courses
python3 -m imkh units grade8                 # units in a course
python3 -m imkh lessons grade8 1             # lessons in a unit
python3 -m imkh get 8.1.2                    # read a lesson
python3 -m imkh search "scientific notation" # search titles
```

References are `course.unit.lesson`: `8.1.2`, `alg1.3.5`. Drop the lesson for a
unit overview (`8.1`). Course names are forgiving — `8`, `grade8`, `Grade 8`,
and `MS/3` all mean Grade 8.

### Other pages

```bash
python3 -m imkh get 8.1.2 --page preparation.html   # goals, standards, materials
python3 -m imkh get 8.1.2 --page practice.html      # practice problems
python3 -m imkh get 8.1   --page assessments.html   # unit assessments
python3 -m imkh get 8.1.2 --audience students       # student-facing version
```

### Full-text search

Title search works out of the box. Searching inside lesson bodies requires
caching a course first:

```bash
python3 -m imkh sync grade8                                  # ~2 minutes
python3 -m imkh search "number talk" --fulltext --course grade8
```

Add `--json` to any read command to get structured output instead of text.

## How it works

```
imkh/
  http.py      cached, rate-limited fetching (0.5s between live requests)
  refs.py      "Grade 8" / "8" / "MS/3" -> family + course number
  parse.py     HTML -> structured index data and Markdown
  catalog.py   course -> unit -> lesson catalog (data/catalog.json)
  render.py    lesson and unit documents with source URLs
  search.py    title search and cached full-text search
  cli.py       the command line interface
```

Every page fetched is cached under `data/cache/` (gitignored), so repeat reads
are instant and offline. Live requests are spaced out and retried with backoff.

## Scope and limits

This reads the **public** IM site only. It does not log in, store credentials,
or bypass any access control.

- **Student Responses (answer keys) are gated on every lesson.** They require a
  free Kendall Hunt teacher registration that this toolkit does not have; the
  output marks those spots `_[Gated: ...]_` rather than silently omitting them.
  If you register, the answer keys stay on the site — this tool just won't fetch
  them for you.
- **K–5 is not on this site**, so the toolkit covers 6–12 only.
- **Diagrams are image URLs**, not viewable images. Alt text and the URL come
  through; the agent is instructed not to describe a diagram it hasn't seen.

Illustrative Mathematics content is published by Kendall Hunt under its own
terms; this toolkit is a reader for material that is already publicly available,
intended for classroom planning. Check Kendall Hunt's terms before
redistributing anything it retrieves.
