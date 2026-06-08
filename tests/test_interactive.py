import sys
import time

from src.interactive import start_quit_listener


class _FakeStdin:
    def __init__(self, lines, tty=True):
        self._lines = list(lines)
        self._tty = tty

    def isatty(self):
        return self._tty

    def readline(self):
        if not self._lines:
            return ""
        return self._lines.pop(0)


def test_q_sets_event(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(["q\n"]))
    event = start_quit_listener()
    for _ in range(100):
        if event.is_set():
            break
        time.sleep(0.05)
    assert event.is_set()


def test_other_input_ignored(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(["hello\n", ""]))
    assert not start_quit_listener().is_set()


def test_headless_never_fires(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(["q\n"], tty=False))
    assert not start_quit_listener().is_set()


def test_eof_exits_cleanly(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin([]))
    assert not start_quit_listener().is_set()
