from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

_BASE_RE = re.compile(r"(480p|720p|1080p)", re.IGNORECASE)
_SIZE_RE = re.compile(r"\[([^\]]*(?:MB|GB)[^\]]*)\]", re.IGNORECASE)
_SEASON_RE = re.compile(r"Season\s+(\d+)", re.IGNORECASE)


@dataclass
class TitleOption:
    """One downloadable variant parsed from a detail page."""

    quality: str  # canonical label matching detect_resolution(), e.g. "720p", "720px264"
    display: str  # human label for prompts, e.g. "720p x264 [550MB]"
    size: str | None = None
    season: str | None = None
    episode_url: str | None = None
    zip_url: str | None = None
    button_url: str | None = None


def _canonical_quality(text: str) -> str | None:
    """Map quality tokens to the detect_resolution() label set."""
    m = _BASE_RE.search(text)
    if not m:
        return None
    base = m.group(1).lower()
    lowered = text.lower()
    if "10bit" in lowered or "10 bit" in lowered:
        return base + "bit"
    if "x264" in lowered:
        return base + "x264"
    if "x265" in lowered:
        # No x265 bucket downstream; closest match is the plain base label.
        return base
    return base


def _display_quality(text: str, size: str | None) -> str:
    m = _BASE_RE.search(text)
    base = m.group(1) if m else text.strip()
    lowered = text.lower()
    if "10bit" in lowered or "10 bit" in lowered:
        base += " 10Bit"
    elif "x264" in lowered:
        base += " x264"
    elif "x265" in lowered:
        base += " x265"
    return f"{base} [{size}]" if size else base


def _quality_size(text: str) -> tuple[str | None, str | None]:
    size_m = _SIZE_RE.search(text)
    return _canonical_quality(text), size_m.group(1) if size_m else None


def _content(soup: BeautifulSoup):
    """Scope parsing to the post body so related-posts/sidebar never leak in."""
    return soup.select_one(".thecontent") or soup


def parse_series_options(html: str) -> list[TitleOption]:
    """Parse `### Season S ... QUALITY [SIZE]` blocks + Episode/Zip links."""
    soup = BeautifulSoup(html, "html.parser")
    options: list[TitleOption] = []
    for heading in _content(soup).find_all(["h2", "h3", "h4"]):
        text = heading.get_text(" ", strip=True)
        season_m = _SEASON_RE.search(text)
        quality, size = _quality_size(text)
        if not season_m or not quality:
            continue
        episode_url = zip_url = None
        for sib in heading.find_next_siblings():
            if sib.name in ("h2", "h3", "h4"):
                break
            anchors = [sib] if sib.name == "a" else sib.find_all("a")
            for a in anchors:
                label = a.get_text(strip=True).lower()
                href = a.get("href")
                if not href:
                    continue
                if "episode" in label and episode_url is None:
                    episode_url = href
                elif ("batch" in label or "zip" in label) and zip_url is None:
                    zip_url = href
            if episode_url and zip_url:
                break
        if episode_url or zip_url:
            options.append(
                TitleOption(
                    quality=quality,
                    display=_display_quality(text, size),
                    size=size,
                    season=season_m.group(1),
                    episode_url=episode_url,
                    zip_url=zip_url,
                )
            )
    return options


def parse_movie_options(html: str) -> list[TitleOption]:
    """Pair each Download-Links button with the quality label preceding it."""
    soup = BeautifulSoup(html, "html.parser")
    options: list[TitleOption] = []
    pending: tuple[str, str | None] | None = None
    for el in _content(soup).descendants:
        if getattr(el, "name", None) == "a" and "maxbutton-download-links" in (
            el.get("class") or []
        ):
            href = el.get("href")
            if href and pending:
                quality, size = pending
                text = f"{quality} [{size}]" if size else quality
                options.append(
                    TitleOption(
                        quality=quality,
                        display=_display_quality(text, size),
                        size=size,
                        button_url=href,
                    )
                )
                pending = None
        elif getattr(el, "name", None) is None:  # text node
            quality, size = _quality_size(str(el))
            if quality:
                pending = (quality, size)
    return options


def seasons_available(options: list[TitleOption]) -> list[str]:
    """Unique seasons in first-seen order."""
    seen: dict[str, None] = {}
    for o in options:
        if o.season and o.season not in seen:
            seen[o.season] = None
    return list(seen.keys())


@dataclass
class SingleRequest:
    """One interactive single-title run: what to fetch and what to skip."""

    post_url: str
    image_url: str
    episode_urls: set[str] | None = None
    zip_urls: set[str] | None = None
    button_urls: set[str] | None = None
    ongoing: bool = False
    scope: str = "all"  # all | episodes | specific | zip
    episode_indices: list[int] | None = None  # 0-based, only for scope == "specific"
    title: str = ""
    refresh: bool = False  # True = scrape even when stored links exist


def parse_season_episode_counts(html: str) -> dict[str, int]:
    """Map season -> episode count from `Season: 1, 2 / Episodes: 9, 7` text.

    The page repeats these labels (description block + Series Info block),
    so the longest match of each wins.
    """
    text = _content(BeautifulSoup(html, "html.parser")).get_text(" ", strip=True)
    season_hits = re.findall(r"Season\s*:\s*([\d,\s]+)", text, re.IGNORECASE)
    episode_hits = re.findall(r"Episodes\s*:\s*([\d,\s]+)", text, re.IGNORECASE)
    if not season_hits or not episode_hits:
        return {}
    seasons = max(season_hits, key=lambda h: len(h.split(","))).split(",")
    episodes = max(episode_hits, key=lambda h: len(h.split(","))).split(",")
    counts: dict[str, int] = {}
    for s, e in zip(seasons, episodes, strict=False):
        if s.strip().isdigit() and e.strip().isdigit():
            counts[s.strip()] = int(e.strip())
    return counts


def parse_episode_selection(text: str, total: int) -> list[int] | None:
    """Parse `1-3,5` style input into 0-based indices. None if invalid."""
    picked: set[int] = set()
    try:
        for part in text.split(","):
            part = part.strip()
            if not part:
                return None
            if "-" in part:
                lo_s, hi_s = part.split("-", 1)
                lo, hi = int(lo_s), int(hi_s)
                if lo < 1 or hi > total or lo > hi:
                    return None
                picked.update(range(lo - 1, hi))
            else:
                n = int(part)
                if n < 1 or n > total:
                    return None
                picked.add(n - 1)
    except ValueError:
        return None
    return sorted(picked) if picked else None
