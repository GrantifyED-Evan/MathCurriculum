"""Polite, cached HTTP access to accessim.org.

Every page is cached under data/cache/accessim/, so repeat runs are instant and
work offline. Live requests are spaced out and retried with backoff.
"""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://accessim.org"
USER_AGENT = "lessonplan/1.0 (+local classroom planning tool; reads public accessim.org pages)"
REQUEST_DELAY = 0.5
MAX_RETRIES = 4
TIMEOUT = 30

_last_request_at = 0.0


class FetchError(RuntimeError):
    """Raised when a page cannot be retrieved after retries."""


class NotFound(FetchError):
    """Raised for a 404."""


def cache_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "cache" / "accessim"


def _cache_path(path: str) -> Path:
    return cache_root() / (path.strip("/") or "index") / "teacher.html"


def url_for(path: str) -> str:
    return f"{BASE_URL}{path}?a=teacher"


def fetch(path: str, *, refresh: bool = False) -> str:
    """Return the teacher-view HTML for a site path such as "/6-8/grade-8/unit-1"."""
    global _last_request_at
    cached = _cache_path(path)
    if not refresh and cached.exists():
        return cached.read_text(encoding="utf-8")

    url = url_for(path)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Encoding": "gzip"}
    )
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        wait = REQUEST_DELAY - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            body = raw.decode("utf-8", errors="replace")
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(body, encoding="utf-8")
            return body
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound(f"404 Not Found: {url}") from exc
            if 400 <= exc.code < 500:
                raise FetchError(f"HTTP {exc.code} for {url}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** (attempt + 1))
    raise FetchError(f"Could not fetch {url} after {MAX_RETRIES} attempts: {last_error}")
