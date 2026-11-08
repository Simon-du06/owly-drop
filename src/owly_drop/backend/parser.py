# SPDX-License-Identifier: MIT
"""Turns the lines the `owly` command prints into events.

This follows what owly 0.4.x prints (crates/owly-cli/src/radio.rs and airdrop.rs in
https://github.com/t4t5/owly). It is plain Python with no GLib, so it is easy to test.
Names and paths come from the sender's device: they are only ever displayed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A string as Rust's {:?} prints it, and an Option<String> printed the same way.
_QUOTED = r'"(?:[^"\\]|\\.)*"'
_MAYBE_QUOTED = rf"(?:Some\({_QUOTED}\)|{_QUOTED}|None)"
_RUST_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'"}

PROMPT = "accept? [y/N]"


def unquote(text: str) -> str:
    """Undoes Rust's {:?} escaping: ``"a\\"b"`` gives ``a"b``, ``Some("x")`` gives ``x``."""
    text = text.strip()
    if text == "None":
        return ""
    if match := re.fullmatch(r"Some\((.*)\)", text):
        text = match.group(1)
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        return text
    body, out, i = text[1:-1], [], 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            if escape := re.match(r"\\u\{([0-9a-fA-F]+)\}", body[i:]):
                out.append(chr(int(escape.group(1), 16)))
                i += escape.end()
                continue
            out.append(_RUST_ESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


# --------------------------------------------------------------- owly radio up


@dataclass(frozen=True)
class RadioUp:
    interface: str


@dataclass(frozen=True)
class PeersChanged:
    peers: tuple[str, ...]


@dataclass(frozen=True)
class RadioDown:
    reason: str


@dataclass(frozen=True)
class RadioError:
    message: str


RadioEvent = RadioUp | PeersChanged | RadioDown | RadioError

_RADIO_UP = re.compile(r"^(\S+) is up: ")
_PEERS = re.compile(r"^peers: (.*)$")
_RADIO_DOWN = "owly: the radio went down: "


def parse_radio(line: str) -> RadioEvent | None:
    """A line from `owly radio up`, which prints everything on stderr."""
    if match := _RADIO_UP.match(line):
        return RadioUp(match.group(1))
    if match := _PEERS.match(line):
        peers = match.group(1).strip()
        return PeersChanged(() if peers == "none" else tuple(peers.split(", ")))
    if line.startswith(_RADIO_DOWN):
        return RadioDown(line[len(_RADIO_DOWN) :])
    if line.startswith("owly: "):
        return RadioError(line[len("owly: ") :])
    return None


# --------------------------------------------------------------- owly receive


@dataclass(frozen=True)
class ReceiverReady:
    name: str


@dataclass(frozen=True)
class RequestStarted:
    sender: str
    model: str


@dataclass(frozen=True)
class OfferedFile:
    name: str
    type: str
    size: int | None


@dataclass(frozen=True)
class OfferedUrl:
    url: str


@dataclass(frozen=True)
class Prompt:
    pass


@dataclass(frozen=True)
class RequestTimedOut:
    pass


@dataclass(frozen=True)
class RequestWithdrawn:
    pass


@dataclass(frozen=True)
class TransferFailed:
    reason: str


@dataclass(frozen=True)
class ReceivedFile:
    path: str


@dataclass(frozen=True)
class ReceivedUrl:
    url: str


ReceiveEvent = (
    ReceiverReady
    | RequestStarted
    | OfferedFile
    | OfferedUrl
    | Prompt
    | RequestTimedOut
    | RequestWithdrawn
    | TransferFailed
)

_RECEIVING_AS = re.compile(rf"^receiving as ({_QUOTED}) ")
_REQUEST = re.compile(rf"^({_MAYBE_QUOTED}) \(({_MAYBE_QUOTED})\) wants to send:$")
_OFFERED_FILE = re.compile(rf"^  ({_QUOTED}) (\S+)\s*(?:(\d+) bytes)?$")
_OFFERED_URL = re.compile(rf"^  ({_QUOTED})$")
_TRANSFER_FAILED = "transfer failed: "


def is_prompt(text: str) -> bool:
    """Whether `owly receive` is waiting for y or n (its prompt has no newline)."""
    return text.strip() == PROMPT


def parse_receive(line: str) -> ReceiveEvent | None:
    """A line from `owly receive` on stderr."""
    if match := _RECEIVING_AS.match(line):
        return ReceiverReady(unquote(match.group(1)))
    if match := _REQUEST.match(line):
        return RequestStarted(unquote(match.group(1)), unquote(match.group(2)))
    if match := _OFFERED_FILE.match(line):
        size = int(match.group(3)) if match.group(3) else None
        return OfferedFile(unquote(match.group(1)), match.group(2), size)
    if match := _OFFERED_URL.match(line):
        return OfferedUrl(unquote(match.group(1)))
    if is_prompt(line):
        return Prompt()
    if line.strip() == "timed out":
        return RequestTimedOut()
    if line == "the request was withdrawn":
        return RequestWithdrawn()
    if line.startswith(_TRANSFER_FAILED):
        return TransferFailed(line[len(_TRANSFER_FAILED) :])
    return None


def parse_received(line: str) -> ReceivedFile | ReceivedUrl:
    """A line from `owly receive` on stdout: a saved file's path, or a quoted link."""
    if line.startswith('"'):
        return ReceivedUrl(unquote(line))
    return ReceivedFile(line)


# --------------------------------------------------------------- owly browse


@dataclass(frozen=True)
class FoundReceiver:
    service_id: str
    name: str
    address: str


_BROWSE = re.compile(rf"^(\S+)\s+({_QUOTED}) \((.*)\)$")


def parse_browse(line: str) -> FoundReceiver | None:
    """A line from `owly browse` on stdout."""
    if match := _BROWSE.match(line):
        return FoundReceiver(match.group(1), unquote(match.group(2)), match.group(3))
    return None


# --------------------------------------------------------------- owly send


@dataclass(frozen=True)
class SendConnecting:
    pass


@dataclass(frozen=True)
class SendAccepted:
    pass


@dataclass(frozen=True)
class SendProgress:
    sent: int
    total: int


@dataclass(frozen=True)
class SendOutcome:
    result: str  # "delivered", "declined" or "failed"
    reason: str = ""


SendEvent = SendConnecting | SendAccepted | SendProgress | SendOutcome

_PROGRESS = re.compile(r"^(\d+) / (\d+) bytes$")


def parse_send_progress(text: str) -> SendProgress | None:
    """The progress `owly send` rewrites in place with \\r."""
    if match := _PROGRESS.match(text.strip()):
        return SendProgress(int(match.group(1)), int(match.group(2)))
    return None


def parse_send(stream: str, line: str) -> SendEvent | None:
    """A line from `owly send`: its outcome on stdout ("out"), the rest on stderr ("err")."""
    if stream == "out":
        if line in ("delivered", "declined"):
            return SendOutcome(line)
        if line.startswith("failed: "):
            return SendOutcome("failed", line[len("failed: ") :])
        return None
    if line.startswith("sending to "):
        return SendConnecting()
    if line == "accepted":
        return SendAccepted()
    return parse_send_progress(line)
