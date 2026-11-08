# SPDX-License-Identifier: MIT
"""Looking for nearby iPhones that will take files: `owly browse`."""

from __future__ import annotations

import signal

from gi.repository import GObject

from . import parser
from .process import OwlyProcess, owly_command


class Browser(GObject.Object):
    """Lists nearby receivers. The radio must be up.

    Signals: log(source, line), found(service_id, name) once per receiver, finished().
    """

    __gtype_name__ = "OwlyDropBrowser"
    __gsignals__ = {
        "log": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "found": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, name: str, seconds: int = 10, owly: str | None = None) -> None:
        super().__init__()
        self.name = name
        self.seconds = seconds
        self.owly = owly or owly_command()
        self.found: dict[str, str] = {}
        self._proc: OwlyProcess | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None

    def start(self) -> None:
        """Starts (again) looking. Raises OwlyError if owly can't be run."""
        if self._proc:
            return
        self.found.clear()
        argv = [self.owly, "browse", "--seconds", str(self.seconds), "--name", self.name]
        self._proc = OwlyProcess(argv, self._on_line, self._on_exit)

    def stop(self) -> None:
        if self._proc:
            self._proc.send_signal(signal.SIGINT)

    def _on_line(self, stream: str, line: str) -> None:
        self.emit("log", "browse", line)
        found = parser.parse_browse(line) if stream == "out" else None
        if found and found.service_id not in self.found:
            self.found[found.service_id] = found.name
            self.emit("found", found.service_id, found.name)

    def _on_exit(self, _code: int) -> None:
        self._proc = None
        self.emit("finished")
