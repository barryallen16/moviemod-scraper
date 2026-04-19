from __future__ import annotations

# Resolution detection patterns, ordered most-specific to least-specific.
# Each tuple: (list_of_substrings_to_match, resolution_label)
_RES_PATTERNS: list[tuple[list[str], str]] = [
    (["720p 10bit", "720p.10bit", "720p.bluray.10bit", "720.10bit"], "720pbit"),
    (["1080p 10bit", "1080p.10bit", "1080p.bluray.10bit", "1080.10bit"], "1080pbit"),
    (["480p.x264", "480.x264"], "480px264"),
    (["720p.x264", "720.x264"], "720px264"),
    (["1080p.x264", "1080.x264"], "1080px264"),
    (["480p", "480"], "480p"),
    (["720p", "720"], "720p"),
    (["1080p", "1080"], "1080p"),
]

SEASON_MAP: dict[str, str] = {f"s{i:02d}": str(i) for i in range(1, 35)}
EPISODE_MAP: dict[str, str] = {f"e{i:02d}": str(i) for i in range(1, 35)}


def detect_resolution(text: str) -> str | None:
    """Detect video resolution from a filename/description string.

    Returns a label like "720p", "1080pbit", "480px264", or None if unknown.
    Input should already be lowercased.
    """
    for patterns, label in _RES_PATTERNS:
        if any(p in text for p in patterns):
            return label
    return None


def parse_season(text: str) -> str | None:
    """Extract season number from text containing patterns like 's01', 's02'.

    Returns the season number as a string, or None if not found.
    """
    for identifier, value in SEASON_MAP.items():
        if identifier in text:
            return value
    return None
