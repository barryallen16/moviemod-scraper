from src.introspect import (
    filter_stored,
    parse_episode_selection,
    parse_movie_options,
    parse_season_episode_counts,
    parse_series_options,
    parse_stored_captions,
    seasons_available,
)

SERIES_HTML = """
<div class="thecontent clearfix">
<h3>Season 1 {Hindi-English} 480p x264 Esubs [220MB]</h3>
<a href="https://episodes.modpro.blog/archives/1">Episode Links</a>
<a href="https://episodes.modpro.blog/archives/2">Batch/Zip File</a>
<h3>Season 1 {Hindi-English} 720p 10Bit Esubs [400MB]</h3>
<p><a href="https://episodes.modpro.blog/archives/3">Episode Links</a>
<a href="https://episodes.modpro.blog/archives/4">Batch/Zip File</a></p>
<h3>Season 2 {Hindi-English} 1080p x264 Esubs [1.5GB]</h3>
<a href="https://episodes.modpro.blog/archives/5">Episode Links</a>
<a href="https://episodes.modpro.blog/archives/6">Batch/Zip File</a>
<h3>Related Posts</h3>
<a href="https://moviesmod.ai.in/download-other/">Download Other 720p [999MB]</a>
</div>
"""

MOVIE_HTML = """
<div class="thecontent clearfix">
<div>Download Flash Point (2007) { English-Hindi } 480p x264 [290MB]
<a class="maxbutton-1 maxbutton maxbutton-download-links" href="https://links.modpro.blog/archives/9467">Download Links</a>
Download Flash Point (2007) { English-Hindi } 720p 10bit [510MB]
<a class="maxbutton-1 maxbutton maxbutton-download-links" href="https://links.modpro.blog/archives/9469">Download Links</a>
</div>
</div>
<div class="sidebar">
<a class="maxbutton-1 maxbutton maxbutton-download-links" href="https://links.modpro.blog/archives/999">Download Links</a>
</div>
"""


class TestParseSeriesOptions:
    def test_three_blocks_parsed(self):
        assert len(parse_series_options(SERIES_HTML)) == 3

    def test_first_block_fields(self):
        o = parse_series_options(SERIES_HTML)[0]
        assert o.season == "1"
        assert o.quality == "480px264"
        assert o.size == "220MB"
        assert o.episode_url == "https://episodes.modpro.blog/archives/1"
        assert o.zip_url == "https://episodes.modpro.blog/archives/2"

    def test_10bit_canonical_label(self):
        o = parse_series_options(SERIES_HTML)[1]
        assert o.quality == "720pbit"
        assert o.size == "400MB"

    def test_season_2_block(self):
        o = parse_series_options(SERIES_HTML)[2]
        assert (o.season, o.quality) == ("2", "1080px264")

    def test_related_posts_ignored(self):
        urls = [
            u
            for o in parse_series_options(SERIES_HTML)
            for u in (o.episode_url, o.zip_url)
        ]
        assert not any("download-other" in (u or "") for u in urls)

    def test_seasons_available_order(self):
        assert seasons_available(parse_series_options(SERIES_HTML)) == ["1", "2"]


class TestParseMovieOptions:
    def test_two_buttons_paired(self):
        opts = parse_movie_options(MOVIE_HTML)
        assert len(opts) == 2

    def test_first_button_fields(self):
        o = parse_movie_options(MOVIE_HTML)[0]
        assert o.quality == "480px264"
        assert o.size == "290MB"
        assert o.button_url == "https://links.modpro.blog/archives/9467"

    def test_second_button_10bit(self):
        o = parse_movie_options(MOVIE_HTML)[1]
        assert o.quality == "720pbit"
        assert o.button_url == "https://links.modpro.blog/archives/9469"

    def test_sidebar_button_without_label_ignored(self):
        urls = [o.button_url for o in parse_movie_options(MOVIE_HTML)]
        assert "https://links.modpro.blog/archives/999" not in urls


COUNTS_HTML = """
<div class="thecontent clearfix">
<ul><li><strong>Description</strong></li></ul>
<p>Name: The Scandal Season: 1 Episodes: 08 Language: Multi</p>
<h3>Series Info:</h3>
<ul>
<li>Season: 1, 2</li>
<li>Episodes: 9, 7</li>
</ul>
</div>
"""


class TestParseSeasonEpisodeCounts:
    def test_prefers_longest_match(self):
        assert parse_season_episode_counts(COUNTS_HTML) == {"1": 9, "2": 7}

    def test_missing_labels(self):
        assert parse_season_episode_counts("<div class='thecontent'><p>hi</p></div>") == {}

    def test_single_season(self):
        html = "<div class='thecontent'><p>Season: 3 Episodes: 12</p></div>"
        assert parse_season_episode_counts(html) == {"3": 12}


class TestParseEpisodeSelection:
    def test_range_and_single(self):
        assert parse_episode_selection("1-3,5", 8) == [0, 1, 2, 4]

    def test_single(self):
        assert parse_episode_selection("2", 8) == [1]

    def test_full_range(self):
        assert parse_episode_selection("1-8", 8) == list(range(8))

    def test_out_of_range(self):
        assert parse_episode_selection("9", 8) is None

    def test_reversed_range(self):
        assert parse_episode_selection("5-2", 8) is None

    def test_garbage(self):
        assert parse_episode_selection("abc", 8) is None

    def test_empty(self):
        assert parse_episode_selection("", 8) is None

    def test_zero(self):
        assert parse_episode_selection("0", 8) is None


SERIES_CAPTION = """\
Name: The Last Of Us
Season: 1, 2
Episodes: 9, 7
Language: Dual Audio (Hindi-English)
Release Year: 2023
\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605
Season 1
720p x264 - https://driveseed.org/file/aaa
720p x264 - https://driveseed.org/file/bbb"""

ZIP_CAPTION = """\
Name: The Last Of Us
Season: 1, 2
\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605
Season 1
720p x264 - https://driveseed.org/file/ccc"""

MOVIE_CAPTION = """\
Name: Flash Point
Release Year: 2007
\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605
720p - https://driveseed.org/file/ddd
1080p - https://driveseed.org/file/eee"""


class TestParseStoredCaptions:
    def test_series_block(self):
        triples = parse_stored_captions(SERIES_CAPTION)
        assert triples == [
            ("1", "720px264", "https://driveseed.org/file/aaa"),
            ("1", "720px264", "https://driveseed.org/file/bbb"),
        ]

    def test_description_lines_ignored(self):
        triples = parse_stored_captions("Name: X\nSeason: 1, 2\nEpisodes: 9, 7\n")
        assert triples == []

    def test_movie_block_no_season(self):
        triples = parse_stored_captions(MOVIE_CAPTION)
        assert triples == [
            (None, "720p", "https://driveseed.org/file/ddd"),
            (None, "1080p", "https://driveseed.org/file/eee"),
        ]

    def test_empty(self):
        assert parse_stored_captions("") == []


STORED = [
    ("series", SERIES_CAPTION, "https://driveseed.org/file/aaa\nhttps://driveseed.org/file/bbb"),
    ("zip", ZIP_CAPTION, "https://driveseed.org/file/ccc"),
    ("movies", MOVIE_CAPTION, "https://driveseed.org/file/ddd\nhttps://driveseed.org/file/eee"),
]


class TestFilterStored:
    def test_zip_scope_season_quality(self):
        assert filter_stored(STORED, "zip", "1", "720px264", None) == [
            "https://driveseed.org/file/ccc"
        ]

    def test_wrong_season_yields_empty(self):
        assert filter_stored(STORED, "zip", "2", "720px264", None) == []

    def test_episodes_scope_excludes_zip_and_movies(self):
        assert filter_stored(STORED, "episodes", "1", "720px264", None) == [
            "https://driveseed.org/file/aaa",
            "https://driveseed.org/file/bbb",
        ]

    def test_specific_indices(self):
        assert filter_stored(STORED, "specific", "1", "720px264", [1]) == [
            "https://driveseed.org/file/bbb"
        ]

    def test_movie_quality_only(self):
        assert filter_stored(STORED, "all", None, "1080p", None) == [
            "https://driveseed.org/file/eee"
        ]

    def test_all_scope_no_filters(self):
        assert filter_stored(STORED, "all", None, None, None) == [
            "https://driveseed.org/file/aaa",
            "https://driveseed.org/file/bbb",
            "https://driveseed.org/file/ccc",
            "https://driveseed.org/file/ddd",
            "https://driveseed.org/file/eee",
        ]
