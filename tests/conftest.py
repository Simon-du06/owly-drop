# SPDX-License-Identifier: MIT
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gi.repository import GLib  # noqa: E402

FAKE_OWLY = os.path.join(ROOT, "tests", "fake-owly")


@pytest.fixture
def fake_owly(monkeypatch):
    """The path of the fake owly, with its FAKE_OWLY_* variables cleared."""
    for name in list(os.environ):
        if name.startswith("FAKE_OWLY_"):
            monkeypatch.delenv(name)
    return FAKE_OWLY


@pytest.fixture
def wait_for():
    """Runs the GLib main loop until condition() is true, or fails after timeout seconds."""

    def wait(condition, timeout=5.0):
        context = GLib.MainContext.default()
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError("timed out waiting for the condition")
            if not context.iteration(False):
                time.sleep(0.005)

    def spin(seconds):
        """Runs the main loop for that long."""
        deadline = time.monotonic() + seconds
        wait(lambda: time.monotonic() > deadline, timeout=seconds + 5)

    wait.spin = spin
    return wait
