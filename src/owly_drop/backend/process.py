# SPDX-License-Identifier: MIT
"""Runs an `owly` command and reads what it prints, without blocking the main loop."""

from __future__ import annotations

import codecs
import contextlib
import os
import re
from collections.abc import Callable, Sequence

from gi.repository import Gio, GLib

LineHandler = Callable[[str, str], None]
PartialHandler = Callable[[str, str], bool]


class OwlyError(Exception):
    """The owly command couldn't be started."""


def owly_command() -> str:
    """The owly executable: $OWLY_BIN, else `owly` on PATH."""
    return os.environ.get("OWLY_BIN", "owly")


class OwlyProcess:
    """A running command whose stdout ("out") and stderr ("err") are read line by line.

    on_line(stream, line) is called for each complete line. Lines end with \\n or \\r, since
    owly redraws its progress with \\r. on_partial(stream, text) is offered the start of a
    line that has no ending yet, such as a prompt, and returns True if it used it.
    on_exit(code) is called once, after both streams are read and the process is gone;
    the code is -1 if a signal ended the process.
    """

    def __init__(
        self,
        argv: Sequence[str],
        on_line: LineHandler,
        on_exit: Callable[[int], None],
        on_partial: PartialHandler | None = None,
    ) -> None:
        self._on_line = on_line
        self._on_exit = on_exit
        self._on_partial = on_partial
        flags = (
            Gio.SubprocessFlags.STDIN_PIPE
            | Gio.SubprocessFlags.STDOUT_PIPE
            | Gio.SubprocessFlags.STDERR_PIPE
        )
        try:
            self._proc = Gio.Subprocess.new(list(argv), flags)
        except GLib.Error as error:
            raise OwlyError(error.message) from error
        self.running = True
        self.exit_code: int | None = None
        self._pending = 3  # stdout, stderr and the exit
        for name, stream in (
            ("out", self._proc.get_stdout_pipe()),
            ("err", self._proc.get_stderr_pipe()),
        ):
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            self._read(stream, name, {"decoder": decoder, "rest": ""})
        self._proc.wait_async(None, self._on_wait)

    def write(self, text: str) -> None:
        """Writes to the command's stdin."""
        if not self.running:
            return
        try:
            pipe = self._proc.get_stdin_pipe()
            pipe.write_bytes(GLib.Bytes.new(text.encode()), None)
            pipe.flush(None)
        except GLib.Error:
            pass

    def send_signal(self, signum: int) -> None:
        if self.running:
            self._proc.send_signal(signum)

    def kill(self) -> None:
        if self.running:
            self._proc.force_exit()

    def _read(self, stream: Gio.InputStream, name: str, state: dict) -> None:
        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, None, self._on_read, name, state)

    def _on_read(self, stream: Gio.InputStream, result: Gio.AsyncResult, name: str, state: dict):
        try:
            data = stream.read_bytes_finish(result)
        except GLib.Error:
            data = None
        if not data or data.get_size() == 0:
            tail = (state["rest"] + state["decoder"].decode(b"", final=True)).strip("\r\n")
            if tail:
                self._on_line(name, tail)
            self._done_one()
            return
        text = state["rest"] + state["decoder"].decode(data.get_data())
        *lines, state["rest"] = re.split(r"[\r\n]", text)
        for line in lines:
            if line:
                self._on_line(name, line)
        if state["rest"] and self._on_partial and self._on_partial(name, state["rest"]):
            state["rest"] = ""
        self._read(stream, name, state)

    def _on_wait(self, proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        with contextlib.suppress(GLib.Error):
            proc.wait_finish(result)
        self.exit_code = proc.get_exit_status() if proc.get_if_exited() else -1
        self._done_one()

    def _done_one(self) -> None:
        self._pending -= 1
        if self._pending == 0:
            self.running = False
            self._on_exit(self.exit_code)
