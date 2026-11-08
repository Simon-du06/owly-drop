# SPDX-License-Identifier: MIT
"""Being visible to iPhones: `owly radio up`, then `owly receive` on the radio's link."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable

from gi.repository import Gio, GLib, GObject

from . import parser
from .process import OwlyProcess, owly_command

OFF = "off"
STARTING = "starting"
UP = "up"
STOPPING = "stopping"


class Request(GObject.Object):
    """Files or links someone wants to send, waiting for accept() or decline().

    "closed" is emitted once with why: "accepted", "declined", "expired" (owly declines by
    itself after 15 s, so this closes a little before), "withdrawn" by the sender, or
    "cancelled" when the receiver stops.
    """

    __gtype_name__ = "OwlyDropRequest"
    __gsignals__ = {"closed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self, sender: str, model: str, reply: Callable[[bool], None], timeout: float):
        super().__init__()
        self.sender = sender
        self.model = model
        self.files: list[parser.OfferedFile] = []
        self.urls: list[str] = []
        self._reply = reply
        self._timeout = timeout
        self._timer = 0
        self.is_open = False

    @property
    def total_size(self) -> int:
        return sum(f.size or 0 for f in self.files)

    def accept(self) -> bool:
        return self._answer(True)

    def decline(self) -> bool:
        return self._answer(False)

    def _open(self) -> None:
        if self.is_open:
            return
        self.is_open = True
        self._timer = GLib.timeout_add(int(self._timeout * 1000), self._on_timeout)

    def _answer(self, accept: bool) -> bool:
        # Never answer once closed: a late "y" would be read for the next request.
        if not self.is_open:
            return False
        self._reply(accept)
        self._close("accepted" if accept else "declined")
        return True

    def _on_timeout(self) -> bool:
        self._timer = 0
        self._close("expired")
        return GLib.SOURCE_REMOVE

    def _close(self, reason: str) -> None:
        if not self.is_open:
            return
        self.is_open = False
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self.emit("closed", reason)


class Session(GObject.Object):
    """Holds Owly's radio and receives on it.

    Properties: state (OFF, STARTING, UP or STOPPING), receiving (owly receive is ready),
    peer-count, and wifi-off (Owly's exclusive modes take Wi-Fi down; shared mode doesn't).

    Signals:
      log(source, line)              every line owly prints, for a technical log
      request(Request)               someone wants to send; answer it
      incoming(sender)               someone is sending, already accepted (auto-accept)
      received(sender, item, is_url) a file was saved (its path), or a link arrived
      failed(kind, detail)           "radio" stopped by itself, "receiver" stopped by
                                     itself, or a "transfer" failed
      stopped()                      the radio and the receiver are both gone
    """

    __gtype_name__ = "OwlyDropSession"
    __gsignals__ = {
        "log": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "request": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "incoming": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "received": (GObject.SignalFlags.RUN_FIRST, None, (str, str, bool)),
        "failed": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "stopped": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    state = GObject.Property(type=str, default=OFF)
    receiving = GObject.Property(type=bool, default=False)
    peer_count = GObject.Property(type=int, default=0)
    wifi_off = GObject.Property(type=bool, default=False)

    def __init__(
        self,
        owly: str | None = None,
        request_timeout: float = 14.0,
        stop_timeout: float = 10.0,
    ) -> None:
        super().__init__()
        self.owly = owly or owly_command()
        self.request_timeout = request_timeout
        self.stop_timeout = stop_timeout
        self.name = ""
        self.folder = ""
        self.auto_accept = False
        self._radio: OwlyProcess | None = None
        self._receiver: OwlyProcess | None = None
        self._request: Request | None = None
        self._when_up: list[Callable[[], None]] = []
        self._stopping_by_request = False
        self._restart_receiver = False
        self._last_error = ""
        self._stop_timer = 0

    @property
    def busy(self) -> bool:
        """Whether a process is still running (stop() before quitting)."""
        return self._radio is not None or self._receiver is not None

    def configure(self, name: str, folder: str, auto_accept: bool) -> None:
        """Sets what the receiver announces and where it saves; restarts it if it runs."""
        changed = (name, folder, auto_accept) != (self.name, self.folder, self.auto_accept)
        self.name, self.folder, self.auto_accept = name, folder, auto_accept
        if changed and self._receiver and self.state == UP:
            self._restart_receiver = True
            self._receiver.send_signal(signal.SIGINT)

    def start(self) -> None:
        """Brings the radio up. Raises OwlyError if owly can't be run."""
        if self.state != OFF:
            return
        self._stopping_by_request = False
        self._last_error = ""
        self.peer_count = 0
        self.wifi_off = False
        self._radio = OwlyProcess(
            [self.owly, "radio", "up"], self._on_radio_line, self._on_radio_exit
        )
        self.state = STARTING

    def stop(self) -> None:
        """Takes the radio down, which gives Wi-Fi back. "stopped" follows."""
        if not self.busy:
            return
        self._stopping_by_request = True
        self._when_up.clear()
        self.state = STOPPING
        self._cancel_request()
        if self._receiver:
            self._receiver.send_signal(signal.SIGINT)
        if self._radio:
            self._radio.send_signal(signal.SIGTERM)
        if not self._stop_timer:
            self._stop_timer = GLib.timeout_add(int(self.stop_timeout * 1000), self._force_stop)

    def when_up(self, callback: Callable[[], None]) -> None:
        """Calls back once the radio is up, bringing it up first if it is off."""
        if self.state == UP:
            callback()
            return
        self._when_up.append(callback)
        if self.state == OFF:
            self.start()

    # ------------------------------------------------------------- radio

    def _on_radio_line(self, _stream: str, line: str) -> None:
        self.emit("log", "radio", line)
        event = parser.parse_radio(line)
        if isinstance(event, parser.RadioUp):
            self.state = UP
            self._check_wifi()
            self._start_receiver()
            callbacks, self._when_up = self._when_up, []
            for callback in callbacks:
                callback()
        elif isinstance(event, parser.PeersChanged):
            self.peer_count = len(event.peers)
        elif isinstance(event, parser.RadioDown):
            self._last_error = event.reason
        elif isinstance(event, parser.RadioError):
            self._last_error = event.message

    def _on_radio_exit(self, code: int) -> None:
        self.emit("log", "radio", f"exited (code {code})")
        self._radio = None
        self._when_up.clear()
        if self._receiver:
            self.state = STOPPING
            self._receiver.send_signal(signal.SIGINT)
        if not self._stopping_by_request:
            self.emit("failed", "radio", self._last_error)
        self._maybe_stopped()

    def _check_wifi(self) -> None:
        try:
            proc = Gio.Subprocess.new(
                ["nmcli", "-t", "-f", "TYPE,STATE", "device"], Gio.SubprocessFlags.STDOUT_PIPE
            )
        except GLib.Error:
            return  # no NetworkManager: say nothing

        def done(proc: Gio.Subprocess, result: Gio.AsyncResult) -> None:
            try:
                _ok, out, _err = proc.communicate_utf8_finish(result)
            except GLib.Error:
                return
            if self.state == UP:
                self.wifi_off = "wifi:connected" not in (out or "").split()

        proc.communicate_utf8_async(None, None, done)

    # ---------------------------------------------------------- receiver

    def _start_receiver(self) -> None:
        if self._receiver or self.state != UP:
            return
        os.makedirs(self.folder, exist_ok=True)
        argv = [self.owly, "receive", "--dir", self.folder, "--name", self.name]
        if self.auto_accept:
            argv.append("--accept")
        try:
            self._receiver = OwlyProcess(
                argv, self._on_receiver_line, self._on_receiver_exit, self._on_receiver_partial
            )
        except Exception as error:  # OwlyError, or the folder can't be made
            self.emit("log", "receive", str(error))
            self.emit("failed", "receiver", str(error))

    def _on_receiver_line(self, stream: str, line: str) -> None:
        self.emit("log", "receive", line)
        if stream == "out":
            sender = self._request.sender if self._request else ""
            item = parser.parse_received(line)
            if isinstance(item, parser.ReceivedUrl):
                self.emit("received", sender, item.url, True)
            else:
                self.emit("received", sender, item.path, False)
            return
        event = parser.parse_receive(line)
        if isinstance(event, parser.ReceiverReady):
            self.receiving = True
        elif isinstance(event, parser.RequestStarted):
            self._cancel_request()
            self._request = Request(event.sender, event.model, self._reply, self.request_timeout)
            if self.auto_accept:
                self.emit("incoming", event.sender)
        elif isinstance(event, parser.OfferedFile) and self._request:
            self._request.files.append(event)
        elif isinstance(event, parser.OfferedUrl) and self._request:
            self._request.urls.append(event.url)
        elif isinstance(event, parser.Prompt):
            self._ask()
        elif isinstance(event, parser.RequestTimedOut) and self._request:
            self._request._close("expired")
        elif isinstance(event, parser.RequestWithdrawn) and self._request:
            self._request._close("withdrawn")
        elif isinstance(event, parser.TransferFailed):
            self.emit("failed", "transfer", event.reason)

    def _on_receiver_partial(self, _stream: str, text: str) -> bool:
        if not parser.is_prompt(text):
            return False
        self.emit("log", "receive", text.strip())
        self._ask()
        return True

    def _ask(self) -> None:
        request = self._request
        if request and not request.is_open:
            request._open()
            self.emit("request", request)

    def _reply(self, accept: bool) -> None:
        if self._receiver:
            self._receiver.write("y\n" if accept else "n\n")

    def _cancel_request(self) -> None:
        if self._request:
            self._request._close("cancelled")

    def _on_receiver_exit(self, code: int) -> None:
        self.emit("log", "receive", f"exited (code {code})")
        self._receiver = None
        self.receiving = False
        self._cancel_request()
        if self._restart_receiver and self.state == UP:
            self._restart_receiver = False
            self._start_receiver()
            return
        if self.state == UP and not self._stopping_by_request:
            self.emit("failed", "receiver", "")
        self._maybe_stopped()

    # -------------------------------------------------------------- stop

    def _force_stop(self) -> bool:
        self._stop_timer = 0
        for proc in (self._receiver, self._radio):
            if proc:
                self.emit("log", "app", "forcing it to stop")
                proc.kill()
        return GLib.SOURCE_REMOVE

    def _maybe_stopped(self) -> None:
        if self.busy:
            return
        if self._stop_timer:
            GLib.source_remove(self._stop_timer)
            self._stop_timer = 0
        self.receiving = False
        self.peer_count = 0
        self.wifi_off = False
        self.state = OFF
        self.emit("stopped")
