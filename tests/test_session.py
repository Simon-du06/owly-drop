# SPDX-License-Identifier: MIT
"""The session, browser and transfer against tests/fake-owly."""

import os

import pytest

from owly_drop.backend import Browser, OwlyError, Session, Transfer
from owly_drop.backend.session import OFF, UP


@pytest.fixture
def session(fake_owly, tmp_path, wait_for):
    session = Session(owly=fake_owly, request_timeout=5, stop_timeout=3)
    session.configure("Test PC", str(tmp_path), auto_accept=False)
    session.events = []
    for name in ("request", "incoming", "received", "failed", "stopped"):
        session.connect(name, lambda _s, *args, name=name: session.events.append((name, *args)))
    yield session
    if session.busy:
        session.stop()
        wait_for(lambda: not session.busy)


def events(session, name):
    return [args for event, *args in session.events if event == name]


def test_accept_a_file(session, tmp_path, wait_for):
    session.start()
    wait_for(lambda: session.receiving)
    assert session.state == UP
    assert session.peer_count == 1

    wait_for(lambda: events(session, "request"))
    [request] = events(session, "request")[0]
    assert request.sender == "Alice's iPhone"
    assert [f.name for f in request.files] == ["IMG_0001.HEIC"]
    assert request.total_size == 2345678
    closed = []
    request.connect("closed", lambda _r, reason: closed.append(reason))
    assert request.accept()
    assert not request.accept()  # only once

    wait_for(lambda: events(session, "received"))
    path = str(tmp_path / "IMG_0001.HEIC")
    assert events(session, "received") == [["Alice's iPhone", path, False]]
    assert os.path.exists(path)
    assert closed == ["accepted"]

    session.stop()
    wait_for(lambda: events(session, "stopped"))
    assert session.state == OFF
    assert not session.busy
    assert events(session, "failed") == []


def test_decline(session, tmp_path, wait_for):
    session.start()
    wait_for(lambda: events(session, "request"))
    [request] = events(session, "request")[0]
    assert request.decline()
    wait_for.spin(0.5)
    assert events(session, "received") == []
    assert not (tmp_path / "IMG_0001.HEIC").exists()


def test_request_expires_without_answering(session, wait_for):
    session.request_timeout = 0.3
    session.start()
    wait_for(lambda: events(session, "request"))
    [request] = events(session, "request")[0]
    closed = []
    request.connect("closed", lambda _r, reason: closed.append(reason))
    wait_for(lambda: closed)
    assert closed == ["expired"]
    assert not request.accept()


def test_auto_accept(session, tmp_path, wait_for):
    session.configure("Test PC", str(tmp_path), auto_accept=True)
    session.start()
    wait_for(lambda: events(session, "received"))
    assert events(session, "incoming") == [["Alice's iPhone"]]
    assert events(session, "request") == []


def test_a_link(session, monkeypatch, wait_for):
    monkeypatch.setenv("FAKE_OWLY_RECEIVE", "link")
    session.start()
    wait_for(lambda: events(session, "request"))
    [request] = events(session, "request")[0]
    assert request.urls == ['https://example.com/a?b="c"']
    request.accept()
    wait_for(lambda: events(session, "received"))
    assert events(session, "received") == [["Alice's iPhone", 'https://example.com/a?b="c"', True]]


def test_settings_change_restarts_the_receiver(session, tmp_path, wait_for):
    session.start()
    wait_for(lambda: events(session, "request"))
    lines = []
    session.connect("log", lambda _s, source, line: lines.append(line))
    session.configure("Renamed PC", str(tmp_path), auto_accept=False)
    wait_for(lambda: any(line.startswith('receiving as "Renamed PC"') for line in lines))
    assert session.state == UP
    assert events(session, "failed") == []


def test_busy_radio(session, monkeypatch, wait_for):
    monkeypatch.setenv("FAKE_OWLY_RADIO", "busy")
    session.start()
    wait_for(lambda: events(session, "stopped"))
    assert events(session, "failed") == [["radio", "the radio is in use by another session"]]
    assert session.state == OFF


def test_radio_going_down_stops_the_receiver(session, monkeypatch, wait_for):
    monkeypatch.setenv("FAKE_OWLY_RADIO", "drop")
    session.start()
    wait_for(lambda: events(session, "stopped"))
    assert events(session, "failed") == [["radio", "the Wi-Fi card was removed"]]
    assert not session.busy


def test_when_up_starts_the_radio(session, wait_for):
    called = []
    session.when_up(lambda: called.append(session.state))
    wait_for(lambda: called)
    assert called == [UP]


def test_missing_owly(tmp_path):
    session = Session(owly=str(tmp_path / "no-owly"))
    with pytest.raises(OwlyError):
        session.start()
    assert session.state == OFF


def test_browse(fake_owly, wait_for):
    browser = Browser("Test PC", owly=fake_owly)
    found, finished = [], []
    browser.connect("found", lambda _b, sid, name: found.append((sid, name)))
    browser.connect("finished", lambda _b: finished.append(True))
    browser.start()
    wait_for(lambda: finished)
    assert found == [("a1b2c3d4e5f6", "Alice's iPhone"), ("0f9e8d7c6b5a", "Bob's iPad")]
    assert not browser.running


@pytest.mark.parametrize(
    ("mode", "outcome"),
    [
        ("", ("delivered", "")),
        ("declined", ("declined", "")),
        ("failed", ("failed", "the receiver closed the connection")),
    ],
)
def test_send(fake_owly, monkeypatch, wait_for, mode, outcome):
    monkeypatch.setenv("FAKE_OWLY_SEND", mode)
    transfer = Transfer("Alice's iPhone", [__file__], "Test PC", owly=fake_owly)
    statuses, progress, finished = [], [], []
    transfer.connect("status", lambda _t, status: statuses.append(status))
    transfer.connect("progress", lambda _t, sent, total: progress.append((sent, total)))
    transfer.connect("finished", lambda _t, *result: finished.append(result))
    transfer.start()
    wait_for(lambda: finished)
    assert finished == [outcome]
    if mode == "":
        assert statuses == ["connecting", "waiting", "sending"]
        assert progress[-1] == (200, 200)


def test_cancel_a_send(fake_owly, monkeypatch, wait_for):
    monkeypatch.setenv("FAKE_OWLY_SEND", "hang")
    transfer = Transfer("Alice's iPhone", [__file__], "Test PC", owly=fake_owly)
    finished = []
    statuses = []
    transfer.connect("status", lambda _t, status: statuses.append(status))
    transfer.connect("finished", lambda _t, *result: finished.append(result))
    transfer.start()
    wait_for(lambda: "waiting" in statuses)
    transfer.cancel()
    wait_for(lambda: finished)
    assert finished == [("cancelled", "")]
