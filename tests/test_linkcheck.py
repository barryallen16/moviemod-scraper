from unittest.mock import patch

import requests

from src.linkcheck import check_link, partition_alive


def _resp(status, url="https://driveseed.org/file/abc", text=""):
    from types import SimpleNamespace

    return SimpleNamespace(status_code=status, url=url, text=text)


class TestCheckLink:
    def test_head_200_alive(self):
        with patch("src.linkcheck.requests.head", return_value=_resp(200)):
            assert check_link("https://driveseed.org/file/abc") == "alive"

    def test_head_404_dead(self):
        with patch("src.linkcheck.requests.head", return_value=_resp(404)):
            assert check_link("https://driveseed.org/file/rrVahJKsju2zqDaqKqXg") == "dead"

    def test_head_405_falls_back_to_get_with_marker(self):
        with (
            patch("src.linkcheck.requests.head", return_value=_resp(405)),
            patch(
                "src.linkcheck.requests.get",
                return_value=_resp(200, text='<li class="list-group-item">x</li>'),
            ),
        ):
            assert check_link("https://driveseed.org/file/abc") == "alive"

    def test_head_405_get_without_marker_dead(self):
        with (
            patch("src.linkcheck.requests.head", return_value=_resp(405)),
            patch("src.linkcheck.requests.get", return_value=_resp(200, text="<html>gone</html>")),
        ):
            assert check_link("https://driveseed.org/file/abc") == "dead"

    def test_head_500_unknown(self):
        with patch("src.linkcheck.requests.head", return_value=_resp(500)):
            assert check_link("https://driveseed.org/file/abc") == "unknown"

    def test_timeout_unknown(self):
        with patch(
            "src.linkcheck.requests.head", side_effect=requests.Timeout("slow")
        ):
            assert check_link("https://driveseed.org/file/abc") == "unknown"


class TestPartitionAlive:
    def test_groups_verdicts(self):
        with patch(
            "src.linkcheck.check_link", side_effect=["alive", "dead", "unknown"]
        ):
            assert partition_alive(["a", "b", "c"]) == (["a"], ["b"], ["c"])
