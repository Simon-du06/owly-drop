# SPDX-License-Identifier: MIT
"""Sending files to an iPhone: `owly send`."""

from __future__ import annotations

import signal
from collections.abc import Sequence

from gi.repository import GObject

from . import parser
from .process import OwlyProcess, owly_command

CONNECTING = "connecting"  # looking for the receiver
WAITING = "waiting"  # asking the receiver to accept
SENDING = "sending"


class Transfer(GObject.Object):
    """Sends files to one receiver, by name. The radio must be up.

    Signals:
      log(source, line)
      status(status)         CONNECTING, WAITING or SENDING
      progress(sent, total)  in bytes
      finished(outcome, reason)  outcome is "delivered", "declined", "failed" or "cancelled"
    """

    __gtype_name__ = "OwlyDropTransfer"
    __gsignals__ = {
        "log": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "status": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "progress": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_UINT64, GObject.TYPE_UINT64),
        ),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
    }

    def __init__(
        self, receiver: str, paths: Sequence[str], sender_name: str, owly: str | None = None
    ) -> None:
        super().__init__()
        self.receiver = receiver
        self.paths = list(paths)
        self.sender_name = sender_name
        self.owly = owly or owly_command()
        self._proc: OwlyProcess | None = None
        self._outcome: parser.SendOutcome | None = None
        self._last_line = ""
        self._cancelled = False

    def start(self) -> None:
        """Starts sending. Raises OwlyError if owly can't be run."""
        argv = [self.owly, "send", "--to", self.receiver, "--name", self.sender_name, "--"]
        self._proc = OwlyProcess(argv + self.paths, self._on_line, self._on_exit, self._on_partial)
        self.emit("status", CONNECTING)

    def cancel(self) -> None:
        if self._proc:
            self._cancelled = True
            self._proc.send_signal(signal.SIGINT)

    def _on_partial(self, _stream: str, text: str) -> bool:
        progress = parser.parse_send_progress(text)
        if progress:
            self.emit("progress", progress.sent, progress.total)
        return progress is not None

    def _on_line(self, stream: str, line: str) -> None:
        self.emit("log", "send", line)
        event = parser.parse_send(stream, line)
        if isinstance(event, parser.SendOutcome):
            self._outcome = event
        elif isinstance(event, parser.SendConnecting):
            self.emit("status", WAITING)
        elif isinstance(event, parser.SendAccepted):
            self.emit("status", SENDING)
        elif isinstance(event, parser.SendProgress):
            self.emit("progress", event.sent, event.total)
        elif stream == "err":
            self._last_line = line

    def _on_exit(self, code: int) -> None:
        self._proc = None
        if self._outcome:
            self.emit("finished", self._outcome.result, self._outcome.reason)
        elif self._cancelled:
            self.emit("finished", "cancelled", "")
        else:
            self.emit("finished", "failed", self._last_line or f"owly exited with code {code}")
