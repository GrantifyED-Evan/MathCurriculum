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
