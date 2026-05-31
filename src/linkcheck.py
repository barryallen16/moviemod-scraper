from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

_FILE_MARKER = "list-group-item"  # present on live driveseed file pages


def check_link(url: str, timeout: int = 10) -> str:
    """Validate a final download link: 'alive', 'dead', or 'unknown'.

    Dead driveseed links answer HEAD with 404 (their GET returns a 200
    soft-404 page, so GET status alone proves nothing). Anything ambiguous
    (timeouts, 5xx, connection errors) is 'unknown' — never destroy
    stored data on a guess.
    """
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        log.debug("Link check failed (unknown): %s: %s", url[:80], e)
        return "unknown"
    if response.status_code == 404:
        return "dead"
    if response.status_code == 200:
        return "alive"
    if response.status_code != 405:
        return "unknown"
    try:
        page = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        log.debug("Link check failed (unknown): %s: %s", url[:80], e)
        return "unknown"
    if page.status_code == 404 or _FILE_MARKER not in page.text.lower():
        return "dead"
    return "alive"


def partition_alive(urls: list[str], timeout: int = 10) -> tuple[list[str], list[str], list[str]]:
    """Split urls into (alive, dead, unknown), logging each verdict."""
    alive, dead, unknown = [], [], []
    for url in urls:
        verdict = check_link(url, timeout=timeout)
        log.info("%s %s", verdict.upper(), url[:80])
        {"alive": alive, "dead": dead, "unknown": unknown}[verdict].append(url)
    log.info(
        "Link check: %d alive, %d dead, %d unknown of %d",
        len(alive), len(dead), len(unknown), len(urls),
    )
    return alive, dead, unknown
