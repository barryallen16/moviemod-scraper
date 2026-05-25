from __future__ import annotations

import logging
from dataclasses import dataclass

import questionary
import requests
from bs4 import BeautifulSoup

from src.introspect import (
    SingleRequest,
    TitleOption,
    parse_episode_selection,
    parse_movie_options,
    parse_season_episode_counts,
    parse_series_options,
    seasons_available,
)

log = logging.getLogger(__name__)


@dataclass
class SearchCard:
    title: str
    url: str
    image_url: str
    is_series: bool
    ongoing: bool


def search_cards(base_url: str, query: str, limit: int = 10) -> list[SearchCard]:
    """Search the site and return up to `limit` result cards.

    Mirrors the phase-1 page parsers: same article/heading/thumbnail markup.
    """
    q = "+".join(query.split())
    resp = requests.get(f"{base_url}search/{q}", timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    cards: list[SearchCard] = []
    for article in soup.select("article.latestPost")[:limit]:
        heading = article.select_one("h2.title.front-view-title a[href]")
        if not heading:
            continue
        img = article.select_one("div.featured-thumbnail img") or article.select_one("img")
        text = article.get_text(" ", strip=True)
        cards.append(
            SearchCard(
                title=heading.get_text(strip=True),
                url=heading.get("href", ""),
                image_url=img.get("src", "") if img else "",
                is_series="Season" in text,
                ongoing="Added]" in text,
            )
        )
    log.info("Search %r: %d cards", query, len(cards))
    return cards


def fetch_detail(card: SearchCard) -> str:
    """Download the detail page HTML."""
    resp = requests.get(card.url, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_options(card: SearchCard) -> list[TitleOption]:
    """Download the detail page and parse downloadable variants."""
    html = fetch_detail(card)
    if card.is_series:
        return parse_series_options(html)
    return parse_movie_options(html)


def ask_scope() -> str | None:
    return questionary.select(
        "What to fetch?",
        choices=[
            questionary.Choice("Everything (episodes + zip)", value="all"),
            questionary.Choice("All episodes", value="episodes"),
            questionary.Choice("Specific episodes", value="specific"),
            questionary.Choice("Zip file only", value="zip"),
        ],
    ).ask()


def ask_episode_indices(total: int) -> list[int] | None:
    while True:
        raw = questionary.text(f"Episode numbers 1-{total} (e.g. 1-3,5):").ask()
        if raw is None:
            return None
        indices = parse_episode_selection(raw, total)
        if indices is not None:
            return indices
        print("Invalid selection, try something like 1-3,5.")


def ask_stored_or_fresh(count: int) -> str | None:
    """Stored links exist: reuse them or re-scrape? Returns 'stored'/'fresh'."""
    return questionary.select(
        f"Found {count} stored links. Use them or re-scrape fresh?",
        choices=[
            questionary.Choice("Use stored links (fast)", value="stored"),
            questionary.Choice("Re-scrape fresh", value="fresh"),
        ],
    ).ask()


def ask_mode() -> str:
    return questionary.select(
        "What do you want to do?",
        choices=["mass scrape (pages)", "search single title"],
    ).ask()


PICKER_STYLE = questionary.Style(
    [
        ("series", "fg:#ff5f87 bold"),
        ("movie", "fg:#5fafff bold"),
    ]
)


def ask_card(cards: list[SearchCard]) -> SearchCard | None:
    # Choice titles must be str or list[(style, text)] — prompt_toolkit
    # HTML objects crash the renderer, so colors go through style classes.
    choices = []
    for c in cards:
        kind = "series" if c.is_series else "movie"
        choices.append(
            questionary.Choice(
                title=[("", f"{c.title[:90]} "), (f"class:{kind}", f"({kind})")],
                value=c,
            )
        )
    return questionary.select(
        "Pick a title (↑↓ + Enter):", choices=choices, style=PICKER_STYLE
    ).ask()


def ask_option(options: list[TitleOption], what: str) -> TitleOption | None:
    return questionary.select(
        f"Pick {what} (↑↓ + Enter):",
        choices=[questionary.Choice(o.display, value=o) for o in options],
    ).ask()


def run_search_flow(
    base_url: str,
    query: str | None,
    pick: int | None,
    season: str | None = None,
    resolution: str | None = None,
    scope: str | None = None,
    episodes: str | None = None,
) -> SingleRequest | None:
    """Search → pick title → season → scope → resolution. Returns a SingleRequest."""
    if not query:
        query = questionary.text("Movie or series name:").ask()
        if not query:
            return None
    cards = search_cards(base_url, query)
    if not cards:
        log.info("No results for %r", query)
        return None
    card = cards[pick] if pick is not None else ask_card(cards)
    if card is None:
        return None
    log.info("Selected: %s (%s)", card.title, card.url)
    html = fetch_detail(card)
    options = parse_series_options(html) if card.is_series else parse_movie_options(html)
    if not options:
        log.info("No downloadable variants found on %s", card.url)
        return None
    if card.is_series:
        seasons = seasons_available(options)
        if season is None:
            season = seasons[0] if len(seasons) == 1 else questionary.select(
                "Pick season (↑↓ + Enter):", choices=seasons
            ).ask()
            if season is None:
                return None
        candidates = [o for o in options if o.season == season]
        if not candidates:
            log.info("No variants for season %r (have: %s)", season, seasons)
            return None
        if scope is None:
            scope = ask_scope()
            if scope is None:
                return None
        episode_indices: list[int] | None = None
        if scope == "specific":
            total = parse_season_episode_counts(html).get(season)
            if total is None:
                log.info("Unknown episode count for season %s, fetching all episodes", season)
                scope = "episodes"
            elif episodes is not None:
                episode_indices = parse_episode_selection(episodes, total)
                if episode_indices is None:
                    log.info("Invalid --episodes value %r for 1-%d", episodes, total)
                    return None
            else:
                episode_indices = ask_episode_indices(total)
                if episode_indices is None:
                    return None
    else:
        candidates = options
        scope, episode_indices = "all", None
    if resolution is None:
        option = candidates[0] if len(candidates) == 1 else ask_option(candidates, "resolution")
    else:
        option = next(
            (o for o in candidates if o.quality == resolution or resolution in o.display),
            None,
        )
        if option is None:
            log.info("No %r variant (have: %s)", resolution, [o.display for o in candidates])
            return None
    if option is None:
        return None
    log.info("Selected: %s (scope=%s)", option.display, scope)
    return SingleRequest(
        post_url=card.url,
        image_url=card.image_url,
        title=card.title,
        season=season if card.is_series else None,
        quality=option.quality,
        episode_urls={option.episode_url} if option.episode_url and scope != "zip" else None,
        zip_urls={option.zip_url} if option.zip_url and scope in ("all", "zip") else None,
        button_urls={option.button_url} if option.button_url else None,
        ongoing=card.ongoing,
        scope=scope,
        episode_indices=episode_indices,
    )
