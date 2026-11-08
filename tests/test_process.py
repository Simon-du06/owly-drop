# SPDX-License-Identifier: MIT
import signal

import pytest

from owly_drop.backend.process import OwlyError, OwlyProcess


def run(argv, wait_for, on_partial=None, stdin=None):
    lines, codes = [], []
    proc = OwlyProcess(
        argv, lambda stream, line: lines.append((stream, line)), codes.append, on_partial
    )
    if stdin is not None:
        proc.write(stdin)
    wait_for(lambda: codes)
    return proc, lines, codes[0]


def test_lines_from_both_streams(wait_for):
    _proc, lines, code = run(
        ["sh", "-c", "echo out; echo err >&2; printf 'last'; exit 3"], wait_for
    )
    assert ("out", "out") in lines
    assert ("err", "err") in lines
    assert ("out", "last") in lines  # an unfinished last line still counts
    assert code == 3


def test_carriage_returns_split_lines(wait_for):
    _proc, lines, _code = run(["sh", "-c", r"printf '\r1 / 2 bytes\r2 / 2 bytes\n' >&2"], wait_for)
    assert lines == [("err", "1 / 2 bytes"), ("err", "2 / 2 bytes")]


def test_partial_prompt_and_stdin(wait_for):
    prompts = []

    def on_partial(stream, text):
        prompts.append(text)
        return True

    script = "printf 'accept? [y/N] ' >&2; read -r answer; echo \"got $answer\""
    _proc, lines, code = run(["sh", "-c", script], wait_for, on_partial, stdin="y\n")
    assert prompts == ["accept? [y/N] "]
    assert lines == [("out", "got y")]
    assert code == 0


def test_signal_gives_minus_one(wait_for):
    codes = []
    proc = OwlyProcess(["sleep", "10"], lambda *_: None, codes.append)
    proc.send_signal(signal.SIGTERM)
    wait_for(lambda: codes)
    assert codes == [-1]
    assert not proc.running


def test_missing_command():
    with pytest.raises(OwlyError):
        OwlyProcess(["/nonexistent/owly"], lambda *_: None, lambda _code: None)
