# SPDX-License-Identifier: MIT
import pytest

from owly_drop.backend import parser


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"plain"', "plain"),
        ('"Bob\'s \\"iPhone\\""', 'Bob\'s "iPhone"'),
        ('Some("Mac\\u{2019}s")', "Mac’s"),
        ('"tab\\there"', "tab\there"),
        ('"back\\\\slash"', "back\\slash"),
        ("None", ""),
        ("not quoted", "not quoted"),
    ],
)
def test_unquote(text, expected):
    assert parser.unquote(text) == expected


def test_radio_lines():
    up = parser.parse_radio("awdl0 is up: fe80::1%awdl0 (02:00:00:00:00:01). Ctrl-C takes it down.")
    assert up == parser.RadioUp("awdl0")
    assert parser.parse_radio("peers: none") == parser.PeersChanged(())
    assert parser.parse_radio("peers: a (x), b (y)") == parser.PeersChanged(("a (x)", "b (y)"))
    assert parser.parse_radio("owly: the radio went down: gone") == parser.RadioDown("gone")
    assert parser.parse_radio("owly: busy") == parser.RadioError("busy")
    assert parser.parse_radio("bringing the radio up...") is None


def test_request_lines():
    assert parser.parse_receive('"Alice\'s iPhone" ("iPhone") wants to send:') == (
        parser.RequestStarted("Alice's iPhone", "iPhone")
    )
    assert parser.parse_receive('Some("A (b)") (Some("iPhone15,2")) wants to send:') == (
        parser.RequestStarted("A (b)", "iPhone15,2")
    )
    assert parser.parse_receive("None (None) wants to send:") == parser.RequestStarted("", "")
    assert parser.parse_receive('  "IMG_0001.HEIC" public.heic 2345678 bytes') == (
        parser.OfferedFile("IMG_0001.HEIC", "public.heic", 2345678)
    )
    assert parser.parse_receive('  "a b.jpg" public.jpeg ') == (
        parser.OfferedFile("a b.jpg", "public.jpeg", None)
    )
    assert parser.parse_receive('  "https://example.com"') == parser.OfferedUrl(
        "https://example.com"
    )


def test_receiver_status_lines():
    ready = parser.parse_receive('receiving as "My PC" (abc) on [fe80::1]:8771, flags 0x89')
    assert ready == parser.ReceiverReady("My PC")
    assert parser.parse_receive("accept? [y/N] ") == parser.Prompt()
    assert parser.is_prompt("accept? [y/N] ")
    assert not parser.is_prompt("accept?")
    assert parser.parse_receive("timed out") == parser.RequestTimedOut()
    assert parser.parse_receive("the request was withdrawn") == parser.RequestWithdrawn()
    assert parser.parse_receive("transfer failed: reset") == parser.TransferFailed("reset")
    assert parser.parse_receive("seen by fe80::1") is None


def test_received_lines():
    assert parser.parse_received("/home/me/Downloads/a.jpg") == parser.ReceivedFile(
        "/home/me/Downloads/a.jpg"
    )
    assert parser.parse_received('"https://example.com/?q=\\"x\\""') == parser.ReceivedUrl(
        'https://example.com/?q="x"'
    )


def test_browse_lines():
    line = 'a1b2c3d4e5f6   "Alice\'s iPhone" ([fe80::1%awdl0]:8770)'
    assert parser.parse_browse(line) == parser.FoundReceiver(
        "a1b2c3d4e5f6", "Alice's iPhone", "[fe80::1%awdl0]:8770"
    )
    assert parser.parse_browse("looking...") is None


def test_send_lines():
    assert parser.parse_send("out", "delivered") == parser.SendOutcome("delivered")
    assert parser.parse_send("out", "declined") == parser.SendOutcome("declined")
    assert parser.parse_send("out", "failed: nope") == parser.SendOutcome("failed", "nope")
    assert parser.parse_send("err", 'sending to "A" at [fe80::1]:8770') == parser.SendConnecting()
    assert parser.parse_send("err", "accepted") == parser.SendAccepted()
    assert parser.parse_send("err", "100 / 200 bytes") == parser.SendProgress(100, 200)
    assert parser.parse_send("err", "looking for a receiver for 30 s...") is None
