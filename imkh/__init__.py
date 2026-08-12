"""Read-only access to the public Illustrative Mathematics curriculum hosted by Kendall Hunt.

Everything this package touches is the freely available teacher- and student-facing
material at https://im.kendallhunt.com. Nothing here logs in, and nothing here
attempts to reach licence-gated material such as Student Responses or assessments.
"""

__all__ = ["catalog", "http", "parse", "refs", "render", "search"]

BASE_URL = "https://im.kendallhunt.com"
