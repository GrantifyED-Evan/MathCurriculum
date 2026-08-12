"""Tests for the imkh toolkit.

Reference parsing and Markdown conversion are tested against fixtures and never
touch the network. The parser tests that need real pages read them from the
on-disk cache and skip when a course has not been synced.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imkh import http, parse  # noqa: E402
from imkh.refs import LessonRef, parse_ref, resolve_course  # noqa: E402


class TestCourseResolution(unittest.TestCase):
    def test_grade_aliases_all_resolve_to_one_course(self):
        for token in ("8", "g8", "grade8", "Grade 8", "GRADE 8", "8th", "MS/3", "MS-3"):
            with self.subTest(token=token):
                self.assertEqual(resolve_course(token).slug, "grade8")

    def test_high_school_aliases(self):
        self.assertEqual(resolve_course("alg1").slug, "alg1")
        self.assertEqual(resolve_course("Algebra 1").slug, "alg1")
        self.assertEqual(resolve_course("geo").slug, "geometry")
        self.assertEqual(resolve_course("HS/3").slug, "alg2")
        self.assertEqual(resolve_course("Algebra 1 Supports").slug, "alg1supports")

    def test_family_and_grade_numbers_do_not_collide(self):
        # "1" means Grade 6 only via family form; a bare "1" is not a grade.
        self.assertEqual(resolve_course("HS/1").slug, "alg1")
        self.assertEqual(resolve_course("MS/1").slug, "grade6")

    def test_unknown_course_raises(self):
        with self.assertRaises(ValueError):
            resolve_course("calculus")


class TestRefParsing(unittest.TestCase):
    def test_dotted_lesson_ref(self):
        ref = parse_ref("8.1.2")
        self.assertEqual(ref.course.slug, "grade8")
        self.assertEqual((ref.unit, ref.lesson), (1, 2))

    def test_unit_only_ref(self):
        ref = parse_ref("alg1.3")
        self.assertEqual(ref.course.slug, "alg1")
        self.assertEqual(ref.unit, 3)
        self.assertIsNone(ref.lesson)

    def test_separator_forms_agree(self):
        expected = parse_ref("8.1.2")
        for text in (
            "8 1 2",
            "grade8/1/2",
            "MS/3/1/2",
            "Grade 8.1.2",
            "Grade 8 Unit 1 Lesson 2",
            "grade8 U1 L2",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_ref(text), expected)

    def test_multiword_course_names(self):
        self.assertEqual(parse_ref("Algebra 1.2.4"), parse_ref("alg1.2.4"))
        self.assertEqual(
            parse_ref("Algebra 1 Supports Unit 2 Lesson 3"), parse_ref("alg1supports.2.3")
        )

    def test_supports_wins_over_algebra1_prefix(self):
        # "Algebra 1 Supports" must not be read as "Algebra 1" with a stray word.
        self.assertEqual(parse_ref("Algebra 1 Supports 2 3").course.slug, "alg1supports")

    def test_course_without_unit_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_ref("grade8")

    def test_path_construction(self):
        ref = LessonRef(course=resolve_course("grade8"), unit=1, lesson=2)
        self.assertEqual(ref.path(), "/MS/teachers/3/1/2/index.html")
        self.assertEqual(
            ref.path(audience="students", page="practice.html"),
            "/MS/students/3/1/2/practice.html",
        )


class TestMarkdownConversion(unittest.TestCase):
    def test_headings_and_paragraphs(self):
        html = "<main><h2>Launch</h2><p>Arrange students in groups.</p></main>"
        out = parse.to_markdown(parse.extract_main(html))
        self.assertIn("## Launch", out)
        self.assertIn("Arrange students in groups.", out)

    def test_list_item_text_stays_on_the_bullet_line(self):
        html = "<main><ul><li><div>Geometry toolkits</div></li></ul></main>"
        out = parse.to_markdown(parse.extract_main(html))
        self.assertIn("- Geometry toolkits", out)

    def test_navigation_chrome_is_dropped(self):
        html = (
            '<main><nav class="im-c-pagination"><a>17</a></nav>'
            "<p>Real content.</p></main>"
        )
        out = parse.to_markdown(parse.extract_main(html))
        self.assertNotIn("17", out)
        self.assertIn("Real content.", out)

    def test_gated_content_is_labelled(self):
        html = (
            "<main><h3>Student Response</h3><p>Teachers with a valid work email "
            "address can click here to register or sign in for free access to "
            "Student Response.</p></main>"
        )
        out = parse.to_markdown(parse.extract_main(html))
        self.assertIn("Gated", out)
        self.assertNotIn("register or sign in", out)

    def test_images_keep_alt_text_and_url(self):
        html = '<main><p><img alt="A rotated quadrilateral" src="https://x/y"></p></main>'
        out = parse.to_markdown(parse.extract_main(html))
        self.assertIn("![A rotated quadrilateral](https://x/y)", out)


class TestIndexParsing(unittest.TestCase):
    def test_unit_sections_do_not_bleed_between_cards(self):
        html = """<main>
          <a href="/MS/teachers/3/1/index.html">
            <p class="im-c-card__subheading">Rigid Transformations</p>
            <ul><li>Congruence</li></ul>
          </a>
          <a href="/MS/teachers/3/2/index.html">
            <p class="im-c-card__subheading">Dilations</p>
            <ul><li>Slope</li></ul>
          </a>
        </main>"""
        units = parse.parse_course_index(html, "MS", 3)
        self.assertEqual([u.number for u in units], [1, 2])
        self.assertEqual(units[0].sections, ["Congruence"])
        self.assertEqual(units[1].sections, ["Slope"])

    def test_lesson_titles_drop_the_number_badge(self):
        html = """<main>
          <div class="im-c-row__aside"><h4>Rigid Transformations</h4></div>
          <a href="/MS/teachers/3/1/1/preparation.html">
            <span class="im-c-number">1</span><span>Moving in the Plane</span></a>
        </main>"""
        lessons = parse.parse_unit_index(html, "MS", 3, 1)
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0].number, 1)
        self.assertEqual(lessons[0].title, "Moving in the Plane")
        self.assertEqual(lessons[0].section, "Rigid Transformations")


class TestAgainstCachedPage(unittest.TestCase):
    """End-to-end checks against a real cached page, skipped if not synced."""

    LESSON_PATH = "/MS/teachers/3/1/2/index.html"

    def setUp(self):
        if not http.is_cached(self.LESSON_PATH):
            self.skipTest(
                f"{self.LESSON_PATH} not cached; run 'python3 -m imkh sync grade8'"
            )
        self.page = http.fetch(self.LESSON_PATH)

    def test_lesson_title_combines_number_and_name(self):
        parsed = parse.parse_lesson(self.page)
        self.assertEqual(parsed["name"], "Naming the Moves")
        self.assertEqual(parsed["title"], "Lesson 2: Naming the Moves")

    def test_lesson_body_has_the_expected_sections(self):
        body = parse.parse_lesson(self.page)["markdown"]
        for section in ("Warm-up", "Launch", "Student Facing", "Activity Synthesis"):
            with self.subTest(section=section):
                self.assertIn(section, body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
