from unittest.mock import patch

import requests

from src.linkcheck import check_link, partition_alive


def _resp(status, text=""):
    from types import SimpleNamespace

    return SimpleNamespace(status_code=status, text=text)


LIVE_PAGE = '<html><li class="list-group-item">movie.mkv</li></html>'
DEAD_PAGE = "<html><h3>404! Page Not Found</h3>The file you are trying to download is no longer available!</html>"


class TestCheckLink:
    def test_live_page_alive(self):
        with patch("src.linkcheck.requests.get", return_value=_resp(200, LIVE_PAGE)):
            assert check_link("https://driveseed.org/file/abc") == "alive"

    def test_404_marker_dead(self):
        with patch("src.linkcheck.requests.get", return_value=_resp(200, DEAD_PAGE)):
            assert check_link("https://driveseed.org/zfile/bDXuke3VI02Wi9fOtoVR") == "dead"

    def test_status_404_dead(self):
        with patch("src.linkcheck.requests.get", return_value=_resp(404, "")):
            assert check_link("https://driveseed.org/file/abc") == "dead"

    def test_status_500_unknown(self):
        with patch("src.linkcheck.requests.get", return_value=_resp(500, "")):
            assert check_link("https://driveseed.org/file/abc") == "unknown"

    def test_timeout_unknown(self):
        with patch(
            "src.linkcheck.requests.get", side_effect=requests.Timeout("slow")
        ):
            assert check_link("https://driveseed.org/file/abc") == "unknown"


class TestPartitionAlive:
    def test_groups_verdicts(self):
        with patch(
            "src.linkcheck.check_link", side_effect=["alive", "dead", "unknown"]
        ):
            assert partition_alive(["a", "b", "c"]) == (["a"], ["b"], ["c"])
