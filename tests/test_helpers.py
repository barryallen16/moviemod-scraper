from src.helpers import EPISODE_MAP, SEASON_MAP, detect_resolution, parse_season


# --------------------------------------------------------------------------- #
# detect_resolution                                                            #
# --------------------------------------------------------------------------- #
class TestDetectResolution:
    def test_720p_10bit(self):
        assert detect_resolution("movie.name.720p.10bit.bluray") == "720pbit"

    def test_1080p_10bit_space(self):
        assert detect_resolution("movie 1080p 10bit x265") == "1080pbit"

    def test_480p_x264(self):
        assert detect_resolution("movie.480p.x264.mp4") == "480px264"

    def test_720p_x264(self):
        assert detect_resolution("movie.720p.x264.mp4") == "720px264"

    def test_1080p_x264(self):
        assert detect_resolution("movie.1080p.x264.mp4") == "1080px264"

    def test_480p_plain(self):
        assert detect_resolution("movie.480p.dvdrip") == "480p"

    def test_720p_plain(self):
        assert detect_resolution("movie.720p.bluray") == "720p"

    def test_1080p_plain(self):
        assert detect_resolution("movie.1080p.bluray") == "1080p"

    def test_720p_bluray_10bit(self):
        assert detect_resolution("movie.720p.bluray.10bit") == "720pbit"

    def test_1080p_dot_10bit(self):
        assert detect_resolution("movie.1080p.10bit.x265") == "1080pbit"

    def test_no_match(self):
        assert detect_resolution("movie.name.description") is None

    def test_480_without_p(self):
        assert detect_resolution("movie.480.x264") == "480px264"

    def test_720_without_p(self):
        assert detect_resolution("movie.720.10bit") == "720pbit"

    def test_1080_without_p(self):
        assert detect_resolution("movie.1080.bluray") == "1080p"

    def test_priority_10bit_over_plain(self):
        """10bit variants should match before plain resolution."""
        assert detect_resolution("movie.720p.10bit") == "720pbit"

    def test_priority_x264_over_plain(self):
        """x264 variants should match before plain resolution."""
        assert detect_resolution("movie.1080p.x264") == "1080px264"


# --------------------------------------------------------------------------- #
# parse_season                                                                 #
# --------------------------------------------------------------------------- #
class TestParseSeason:
    def test_s01(self):
        assert parse_season("season s01 episode e05") == "1"

    def test_s10(self):
        assert parse_season("season s10") == "10"

    def test_s34(self):
        assert parse_season("s34 something") == "34"

    def test_no_match(self):
        assert parse_season("no season here") is None

    def test_partial_match_ignored(self):
        assert parse_season("bs01 extra") == "1"  # s01 is in bs01


# --------------------------------------------------------------------------- #
# SEASON_MAP / EPISODE_MAP constants                                           #
# --------------------------------------------------------------------------- #
class TestConstants:
    def test_season_map_has_s01_through_s34(self):
        for i in range(1, 35):
            key = f"s{i:02d}"
            assert key in SEASON_MAP
            assert SEASON_MAP[key] == str(i)

    def test_episode_map_has_e01_through_e34(self):
        for i in range(1, 35):
            key = f"e{i:02d}"
            assert key in EPISODE_MAP
            assert EPISODE_MAP[key] == str(i)
