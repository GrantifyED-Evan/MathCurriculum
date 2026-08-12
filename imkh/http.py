"""Polite, cached HTTP access to im.kendallhunt.com.

Pages on the IM site are static and change rarely, so every response is cached on
disk. Repeat runs are served locally, which keeps load off Kendall Hunt's servers
and makes the agent fast and usable offline once a course has been synced.
"""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import BASE_URL

USER_AGENT = (
    "imkh-curriculum-agent/1.0 (+local classroom research tool; "
    "reads public im.kendallhunt.com pages)"
)

# Seconds to wait between live requests. The site is a small static host; there is
# no reason to hammer it.
REQUEST_DELAY = 0.5

MAX_RETRIES = 4
TIMEOUT = 30

_last_request_at = 0.0


class FetchError(RuntimeError):
    """Raised when a page cannot be retrieved after retries."""


class NotFound(FetchError):
    """Raised for a 404 — used to detect the end of a unit or course range."""


def cache_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "cache"


def _cache_path(path: str) -> Path:
    clean = path.lstrip("/")
    if not clean or clean.endswith("/"):
        clean += "index.html"
    return cache_root() / clean


def _sleep_for_rate_limit() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_at = time.monotonic()


def _read_body(response) -> str:
    raw = response.read()
    if response.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def fetch(path: str, *, refresh: bool = False, allow_missing: bool = False) -> str | None:
    """Return the HTML at `path`, using the on-disk cache unless `refresh` is set.

    `path` is site-relative, e.g. "/MS/teachers/3/1/2/index.html". When
    `allow_missing` is true a 404 yields None instead of raising, which lets
    callers probe for the end of a numbered range.
    """
    cached = _cache_path(path)
    if not refresh and cached.exists():
        return cached.read_text(encoding="utf-8")

    url = f"{BASE_URL}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "gzip",
        },
    )

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        _sleep_for_rate_limit()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = _read_body(response)
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(body, encoding="utf-8")
            return body
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                if allow_missing:
                    return None
                raise NotFound(f"404 Not Found: {url}") from exc
            # 4xx other than 404 will not improve on retry.
            if 400 <= exc.code < 500:
                raise FetchError(f"HTTP {exc.code} for {url}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc

        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** (attempt + 1))

    raise FetchError(f"Could not fetch {url} after {MAX_RETRIES} attempts: {last_error}")


def is_cached(path: str) -> bool:
    return _cache_path(path).exists()
