from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

# Dead driveseed pages return HTTP 200 with this marker in the body, e.g.:
#   <h3>404! Page Not Found</h3>
#   "The file you are trying to download is no longer available!"
# NOTE: HEAD status is meaningless here (the server 404s HEAD even for
# live links) and GET status is always 200, so only the body decides.
_DEAD_MARKERS = ("404! page not found", "no longer available")

# Plain requests get tarpitted/blocked; look like the scraper's browser.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    ),
    "Referer": "https://driveseed.org/",
    "Accept": "text/html,application/xhtml+xml",
}


def _fetch(url: str, timeout: int):
    """GET with one retry; returns response or raises the last error."""
    try:
        return requests.get(url, timeout=timeout, allow_redirects=True, headers=_HEADERS)
    except requests.RequestException:
        return requests.get(url, timeout=timeout, allow_redirects=True, headers=_HEADERS)


def check_link(url: str, timeout: int = 15) -> str:
    """Validate a final download link: 'alive', 'dead', or 'unknown'.

    Anything ambiguous (timeouts, blocks, 5xx) is 'unknown' — never
    destroy stored data on a guess.
    """
    try:
        page = _fetch(url, timeout)
    except requests.RequestException as e:
        log.info("UNKNOWN %s (%s)", url[:80], type(e).__name__)
        return "unknown"
    if page.status_code == 404:
        return "dead"
    if page.status_code != 200:
        log.info("UNKNOWN %s (HTTP %s)", url[:80], page.status_code)
        return "unknown"
    body = page.text.lower()
    if any(marker in body for marker in _DEAD_MARKERS):
        return "dead"
    return "alive"


def partition_alive(urls: list[str], timeout: int = 15) -> tuple[list[str], list[str], list[str]]:
    """Split urls into (alive, dead, unknown), logging each verdict."""
    alive, dead, unknown = [], [], []
    for url in urls:
        verdict = check_link(url, timeout=timeout)
        if verdict != "unknown":
            log.info("%s %s", verdict.upper(), url[:80])
        {"alive": alive, "dead": dead, "unknown": unknown}[verdict].append(url)
    log.info(
        "Link check: %d alive, %d dead, %d unknown of %d",
        len(alive), len(dead), len(unknown), len(urls),
    )
    return alive, dead, unknown
