"""Tests for the lessonplan app.

Parsing and plan assembly are tested on small synthetic pages that mimic
accessim.org's streamed markup, so these tests never touch the network. One test
uses a real cached lesson when available and skips otherwise.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lessonplan import courses, fetch, parse, plan, render  # noqa: E402

LESSON_HTML = """<html><body><div class="layout__main">
<div>Unit 1, Lesson 2</div><h1>Naming the Moves</h1>
<template id="B:1"></template>
</div>
<div hidden id="S:1">
<p>2.1</p><h2>Warm-up</h2><div>10 mins</div><h3>Notice and Wonder</h3>
<h4>Instructional Routines</h4><p>Notice and Wonder</p>
<h4>Materials</h4><p>To Gather</p><p>Geometry toolkits</p>
<h3>Activity Narrative</h3><p>Students look at a picture. The purpose of this Warm-up is to describe a move.</p>
<h3>Launch</h3><p>Arrange students in groups of 2. Give 1 minute of quiet think time.</p>
<h3>Student Task Statement</h3><p>What do you notice?</p>
<h3>Activity Synthesis</h3><p>Ask, “What did you notice?”</p>
<template id="P:2"></template>
</div>
<div hidden id="S:2">
<p>2.2</p><h2>Activity</h2><div>25 mins</div><h3>Card Sort</h3>
<h3>Activity Narrative</h3><p>Monitor for groups who sort by type.</p>
<h3>Launch</h3><p>Arrange students in groups of 3.</p>
<p>Engagement: Chunk this task.</p>
<h3>Activity Synthesis</h3><p>Discuss.</p>
<h2>Lesson Synthesis</h2><p>Ask, “What are the three moves called?”</p>
<h2>Student Lesson Summary</h2><p>Moves have names.</p>
<h2>Have feedback on the curriculum?</h2><p>ignored</p>
</div>
<script>$RC("B:1","S:1")</script></body></html>"""

PREP_HTML = """<div class="layout__main"><h1>Naming the Moves</h1>
<h2>Learning Goals</h2><ul><li><p>Describe moves.</p></li></ul>
<h3>Student-Facing Goal</h3><p>Let's describe moves.</p>
<h3>Student-Facing Targets</h3><ul><li>I can name moves.</li></ul>
<h2>Required Materials</h2><h4>Activity 1</h4><ul><li>Geometry toolkits</li></ul>
<h2>Required Preparation</h2><p>Cut cards.</p>
<h3>Standards Alignment</h3><p>Addressing</p><p>8.G.A.1</p><h5>8.G.A.1</h5>
<h2>Glossary</h2><h3>rotation</h3><p>A turn.</p></div>"""


def make_plan(period=45):
    lesson = parse.parse_lesson(LESSON_HTML)
    prep = parse.parse_preparation(PREP_HTML)
    return plan.build(lesson, prep, ref=courses.parse_ref("8.1.2"), unit_title="Rigid Transformations",
                      source_path="/6-8/grade-8/unit-1/section-a/lesson-2", period=period)


class TestRefs(unittest.TestCase):
    def test_parse_ref(self):
        ref = courses.parse_ref("8.1.2")
        self.assertEqual((ref.course.slug, ref.unit, ref.lesson), ("grade8", 1, 2))
        self.assertEqual(courses.parse_ref("alg1.2.4").course.slug, "alg1")
        self.assertIsNone(courses.parse_ref("grade8.3").lesson)
        self.assertEqual(str(courses.parse_ref("grade8.1.2")), "8.1.2")

    def test_bad_ref(self):
        with self.assertRaises(ValueError):
            courses.parse_ref("calculus.1.1")


class TestParse(unittest.TestCase):
    def test_stream_segments_are_placed(self):
        resolved = parse.resolve_stream(LESSON_HTML)
        self.assertIn("Card Sort", resolved)
        self.assertLess(resolved.index("Notice and Wonder"), resolved.index("Card Sort"))

    def test_lesson_structure(self):
        lesson = parse.parse_lesson(LESSON_HTML)
        self.assertEqual(lesson.title, "Naming the Moves")
        self.assertEqual([a.number for a in lesson.activities], ["2.1", "2.2"])
        self.assertEqual([a.minutes for a in lesson.activities], [10, 25])
        warm = lesson.activities[0]
        self.assertEqual(warm.routines, ["Notice and Wonder"])
        self.assertEqual(warm.materials, ["Geometry toolkits (gather)"])
        self.assertEqual(lesson.summary, ["Moves have names."])

    def test_preparation(self):
        prep = parse.parse_preparation(PREP_HTML)
        self.assertEqual(prep.learning_goals, ["Describe moves."])
        self.assertEqual(prep.student_targets, ["I can name moves."])
        self.assertEqual(prep.standards, {"Addressing": ["8.G.A.1"]})
        self.assertEqual(prep.glossary, [("rotation", "A turn.")])


class TestMath(unittest.TestCase):
    def test_latex_to_text(self):
        cases = {
            r"\frac{x+1}{3}": "(x+1)/3",
            r"-2\frac14": "-2 1/4",
            r"\sqrt{2}": "√2",
            r"90^\circ": "90°",
            r"x^{2}+y^{2}": "x^2+y^2",
            r"\begin{cases} y=x+1 \\ y=2x \end{cases}": "y=x+1; y=2x",
        }
        for latex, text in cases.items():
            with self.subTest(latex=latex):
                self.assertEqual(parse.latex_to_text(latex), text)

    def test_mathjax_container_becomes_text(self):
        html = ('<div class="layout__main"><p>Combine (<mjx-container><svg><g data-mml-node="math" '
                'data-latex="2x + 1"></g></svg></mjx-container>)</p></div>')
        self.assertEqual(parse.flatten(html)[0].text, "Combine (2x + 1)")


class TestPlan(unittest.TestCase):
    def test_timeline(self):
        p = make_plan()
        self.assertEqual([(s.start, s.end) for s in p.segments], [(0, 10), (10, 35), (35, 40), (40, 45)])
        self.assertEqual(p.total, 45)
        self.assertTrue(p.segments[-1].suggested_time)

    def test_extraction(self):
        warm, act, synth, _ = make_plan().segments
        self.assertEqual(warm.grouping, "Partners")
        self.assertEqual(act.grouping, "Groups of 3")
        self.assertIn("The purpose of this Warm-up", warm.purpose)
        self.assertEqual(warm.questions, ["What did you notice?"])
        self.assertEqual(act.supports, ["Engagement: Chunk this task."])
        self.assertEqual(act.monitor, ["Monitor for groups who sort by type."])
        self.assertEqual(synth.questions, ["What are the three moves called?"])

    def test_over_time_note(self):
        notes = make_plan(period=40).timing_notes
        self.assertIn("5 min over", notes[0])

    def test_renderers(self):
        p = make_plan()
        md = render.markdown(p)
        self.assertIn("| 0–10 (10 min) | Warm-up 2.1 |", md)
        self.assertIn("CC BY-NC", md)
        self.assertIn("<h1>Lesson 2: Naming the Moves</h1>", render.html_page(p))


class TestCachedLesson(unittest.TestCase):
    def test_real_lesson_if_cached(self):
        path = "/6-8/grade-8/unit-1/section-a/lesson-2"
        if not fetch._cache_path(path).exists():
            self.skipTest("8.1.2 not cached")
        lesson = parse.parse_lesson(fetch.fetch(path))
        self.assertEqual(lesson.title, "Naming the Moves")
        self.assertEqual([a.minutes for a in lesson.activities], [10, 10, 15])


if __name__ == "__main__":
    unittest.main()
