#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owly Drop: a GNOME app for AirDrop between iPhones and Linux, on top of Owly.

It drives the `owly` command-line client (https://github.com/t4t5/owly):
  - `owly radio up`  holds the AWDL radio (Wi-Fi is off meanwhile)
  - `owly receive`   receives files, asking "accept? [y/N]" on stdin
  - `owly browse`    lists nearby iPhones
  - `owly send`      sends files
"""

import codecs
import json
import locale
import os
import re
import shutil
import signal
import sys
import tempfile
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

APP_ID = "io.github.Simon_du06.OwlyDrop"
VERSION = "0.1.0"
OWLY = os.environ.get("OWLY_BIN", "owly")
HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(GLib.get_user_config_dir(), "owly-drop", "settings.json")
PROMPT = "accept? [y/N]"
STOP_TIMEOUT_S = 10

# --------------------------------------------------------------------------
# Translations: po/<lang>.po, read at startup (no compiling needed)
# --------------------------------------------------------------------------

_PO_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
_PLURAL_RULES = {"fr": lambda n: int(n > 1)}
_T = {}
_plural = lambda n: int(n != 1)  # noqa: E731


def _po_unquote(s):
    s = s.strip()
    if len(s) < 2 or s[0] != '"' or s[-1] != '"':
        return ""
    return re.sub(r"\\(.)", lambda m: _PO_ESC.get(m.group(1), m.group(1)), s[1:-1])


def parse_po(path):
    """msgid -> msgstr, and (msgid, msgid_plural) -> [msgstr[0], msgstr[1]]."""
    entries, cur, key = {}, {}, None

    def flush():
        if not cur.get("msgid") or cur.get("fuzzy"):
            return
        if "msgid_plural" in cur:
            forms = [cur.get(f"msgstr[{i}]", "") for i in range(2)]
            if all(forms):
                entries[(cur["msgid"], cur["msgid_plural"])] = forms
        elif cur.get("msgstr"):
            entries[cur["msgid"]] = cur["msgstr"]

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                flush()
                cur, key = {}, None
            elif line.startswith("#"):
                if line.startswith("#,") and "fuzzy" in line:
                    cur["fuzzy"] = True
            elif line.startswith('"'):
                if key:
                    cur[key] += _po_unquote(line)
            else:
                k, _sep, rest = line.partition(" ")
                if k == "msgid" and key and key.startswith("msgstr"):
                    flush()
                    cur = {}
                cur[k], key = _po_unquote(rest), k
    flush()
    return entries


def load_translations():
    global _T, _plural
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            break
    else:
        return
    for lang in value.split(":"):
        lang = lang.split(".")[0].split("@")[0]
        for code in (lang, lang.split("_")[0]):
            if code in ("C", "POSIX", "en", ""):
                return
            path = os.path.join(HERE, "po", f"{code}.po")
            if os.path.exists(path):
                _T = parse_po(path)
                _plural = _PLURAL_RULES.get(code.split("_")[0], _plural)
                return


def _(s):
    return _T.get(s, s)


def ngettext(singular, plural, n):
    forms = _T.get((singular, plural))
    if forms:
        return forms[min(_plural(n), len(forms) - 1)]
    return singular if n == 1 else plural


# --------------------------------------------------------------------------
# Reading owly's output
# --------------------------------------------------------------------------

# A string printed by Rust's {:?}, possibly inside Some(...).
_Q = r'(?:Some\()?"(?:[^"\\]|\\.)*"\)?|None'
RE_UP = re.compile(r"^(\S+) is up: ")
RE_PEERS = re.compile(r"^peers: (.*)$")
RE_REQUEST = re.compile(rf"^({_Q}) \(({_Q})\) wants to send:$")
RE_FILE = re.compile(r'^  ("(?:[^"\\]|\\.)*") (\S+)\s*(?:(\d+) bytes)?$')
RE_URL = re.compile(r'^  ("(?:[^"\\]|\\.)*")$')
RE_BROWSE = re.compile(r'^(\S+)\s+("(?:[^"\\]|\\.)*") \((.*)\)$')
RE_PROGRESS = re.compile(r"^(\d+) / (\d+) bytes$")
_RUST_ESC = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'"}


def rust_unquote(s):
    """Undoes Rust's {:?} escaping: "a\\"b" -> a"b, Some("x") -> x."""
    s = s.strip()
    if s == "None":
        return ""
    m = re.fullmatch(r"Some\((.*)\)", s)
    if m:
        s = m.group(1)
    if not (len(s) >= 2 and s[0] == s[-1] == '"'):
        return s
    s, out, i = s[1:-1], [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            m = re.match(r"\\u\{([0-9a-fA-F]+)\}", s[i:])
            if m:
                out.append(chr(int(m.group(1), 16)))
                i += m.end()
                continue
            out.append(_RUST_ESC.get(s[i + 1], s[i + 1]))
            i += 2
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def human_size(n):
    if n is None:
        return ""
    units = (_("B"), _("KB"), _("MB"), _("GB"))
    for i, unit in enumerate(units):
        if n < 1024 or i == len(units) - 1:
            value = f"{n:.0f}" if i == 0 else locale.format_string("%.1f", n)
            return f"{value} {unit}"
        n /= 1024


def files_label(n):
    return ngettext("{n} file", "{n} files", n).format(n=n)


# --------------------------------------------------------------------------
# One owly process, read line by line without blocking the UI
# --------------------------------------------------------------------------


class OwlyProcess:
    """Runs owly and calls on_line(stream, line) for each stdout/stderr line.

    on_partial(stream, text) gets an unfinished line (a prompt with no
    newline, a progress line ended by \\r) and returns True if it used it.
    on_exit(code) is called once everything is read and the process is gone.
    """

    def __init__(self, argv, on_line, on_exit, on_partial=None):
        self.on_line, self.on_exit, self.on_partial = on_line, on_exit, on_partial
        flags = (
            Gio.SubprocessFlags.STDIN_PIPE
            | Gio.SubprocessFlags.STDOUT_PIPE
            | Gio.SubprocessFlags.STDERR_PIPE
        )
        self.proc = Gio.Subprocess.new(argv, flags)  # GLib.Error if owly is missing
        self.running = True
        self.code = None
        self._pending = 3  # stdout, stderr, process exit
        for name, stream in (("out", self.proc.get_stdout_pipe()), ("err", self.proc.get_stderr_pipe())):
            state = {"dec": codecs.getincrementaldecoder("utf-8")("replace"), "buf": ""}
            self._read(stream, name, state)
        self.proc.wait_async(None, self._on_wait)

    def _read(self, stream, name, state):
        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, None, self._on_read, name, state)

    def _on_read(self, stream, res, name, state):
        try:
            data = stream.read_bytes_finish(res)
        except GLib.Error:
            data = None
        if not data or data.get_size() == 0:
            tail = (state["buf"] + state["dec"].decode(b"", final=True)).strip("\r\n")
            if tail:
                self.on_line(name, tail)
            self._done_one()
            return
        text = state["buf"] + state["dec"].decode(data.get_data())
        parts = re.split(r"[\r\n]", text)
        state["buf"] = parts.pop()
        for line in parts:
            if line:
                self.on_line(name, line)
        if state["buf"] and self.on_partial and self.on_partial(name, state["buf"]):
            state["buf"] = ""
        self._read(stream, name, state)

    def _on_wait(self, proc, res):
        try:
            proc.wait_finish(res)
        except GLib.Error:
            pass
        self.code = proc.get_exit_status() if proc.get_if_exited() else -1
        self._done_one()

    def _done_one(self):
        self._pending -= 1
        if self._pending == 0:
            self.running = False
            self.on_exit(self.code)

    def write(self, text):
        if not self.running:
            return
        try:
            pipe = self.proc.get_stdin_pipe()
            pipe.write_bytes(GLib.Bytes.new(text.encode()), None)
            pipe.flush(None)
        except GLib.Error:
            pass

    def signal(self, sig):
        if self.running:
            self.proc.send_signal(sig)

    def kill(self):
        if self.running:
            self.proc.force_exit()


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def default_name():
    real = GLib.get_real_name()
    if real and real != "Unknown":
        first = real.split()[0]
        return _("{name}'s PC").format(name=first[:1].upper() + first[1:])
    return GLib.get_host_name()


def default_dir():
    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    return d or os.path.expanduser("~/Downloads")


def load_settings():
    s = {"name": default_name(), "dir": default_dir(), "auto_accept": False}
    try:
        with open(CONFIG_FILE) as f:
            s.update({k: v for k, v in json.load(f).items() if k in s})
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------


class Window(Adw.ApplicationWindow):
    def __init__(self, app, selftest=False):
        super().__init__(application=app, title="Owly Drop")
        self.app = app
        self.selftest = selftest
        self.settings = load_settings()
        self.radio = None
        self.receiver = None
        self.radio_state = "off"  # off | starting | up | stopping
        self.receiver_ready = False
        self.restart_receiver = False
        self.user_stopped = False
        self.quitting = False
        self.last_error = None
        self.peer_count = 0
        self.wifi_off = False
        self.after_up = []
        self.request = None
        self.request_dialog = None
        self.request_timer = 0
        self.incoming = []
        self.incoming_timer = 0
        self.received_rows = 0
        self._syncing = False
        self.set_default_size(540, 760)
        self._build()
        self.connect("close-request", self._on_close_request)
        self._update_status()

    # ---------------------------------------------------------------- UI

    def _build(self):
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)
        self.banner = Adw.Banner.new(
            _("Wi-Fi is off while this computer is visible. Turn visibility off to get it back.")
        )
        view.add_top_bar(self.banner)

        self.toasts = Adw.ToastOverlay()
        view.set_content(self.toasts)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.toasts.set_child(scroll)
        clamp = Adw.Clamp(maximum_size=600)
        scroll.set_child(clamp)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(12)
        box.set_margin_end(12)
        clamp.set_child(box)

        # --- Visibility
        group = Adw.PreferencesGroup(title=_("Receive"))
        self.visible_row = Adw.SwitchRow(title=_("Visible to iPhones"))
        self.visible_row.connect("notify::active", self._on_visible_toggled)
        group.add(self.visible_row)
        self.auto_row = Adw.SwitchRow(
            title=_("Accept automatically"),
            subtitle=_("No confirmation dialog"),
            active=self.settings["auto_accept"],
        )
        self.auto_row.connect("notify::active", self._on_auto_toggled)
        group.add(self.auto_row)
        box.append(group)

        # --- Send
        group = Adw.PreferencesGroup(title=_("Send"), description=_("Or drop files onto the window."))
        send_row = Adw.ButtonRow(title=_("Send Files…"), start_icon_name="document-send-symbolic")
        send_row.connect("activated", self._on_send_clicked)
        group.add(send_row)
        self.send_group = group
        box.append(group)

        # --- Received
        self.received_group = Adw.PreferencesGroup(title=_("Received"))
        self.placeholder = Adw.ActionRow(title=_("Nothing received yet"))
        self.placeholder.add_css_class("dim-label")
        self.received_group.add(self.placeholder)
        box.append(self.received_group)

        # --- Settings
        group = Adw.PreferencesGroup(title=_("Settings"))
        self.name_row = Adw.EntryRow(title=_("Name shown on the iPhone"), show_apply_button=True)
        self.name_row.set_text(self.settings["name"])
        self.name_row.connect("apply", self._on_name_applied)
        group.add(self.name_row)
        self.dir_row = Adw.ActionRow(title=_("Download folder"), subtitle=self.settings["dir"])
        btn = Gtk.Button(label=_("Change…"), valign=Gtk.Align.CENTER)
        btn.connect("clicked", self._on_choose_dir)
        self.dir_row.add_suffix(btn)
        group.add(self.dir_row)
        box.append(group)

        # --- Log
        expander = Gtk.Expander(label=_("Technical log"))
        self.log_view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        log_scroll = Gtk.ScrolledWindow(child=self.log_view, min_content_height=180)
        log_scroll.add_css_class("card")
        expander.set_child(log_scroll)
        box.append(expander)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

        self.set_content(view)

    def log(self, source, line):
        buf = self.log_view.get_buffer()
        buf.insert(buf.get_end_iter(), f"{time.strftime('%H:%M:%S')} [{source}] {line}\n")
        excess = buf.get_line_count() - 600
        if excess > 0:
            buf.delete(buf.get_start_iter(), buf.get_iter_at_line(excess)[1])
        if self.selftest:
            print(f"  [{source}] {line}")

    def toast(self, text, timeout=4):
        t = Adw.Toast.new(text)
        t.set_timeout(timeout)
        self.toasts.add_toast(t)

    def notify(self, nid, title, body, buttons=()):
        if self.selftest or self.is_active():
            return
        n = Gio.Notification.new(title)
        n.set_body(body)
        for label, action in buttons:
            n.add_button(label, action)
        if buttons:
            n.set_priority(Gio.NotificationPriority.HIGH)
        self.app.send_notification(nid, n)

    def _update_status(self):
        st = self.radio_state
        if st == "off":
            sub = _("Off")
        elif st == "starting":
            sub = _("Starting the radio…")
        elif st == "stopping":
            sub = _("Stopping… Wi-Fi is coming back")
        elif not self.receiver_ready:
            sub = _("Radio up, starting the receiver…")
        else:
            sub = _("Visible: on the iPhone, tap Share, then AirDrop")
            if self.peer_count:
                n = self.peer_count
                sub += " · " + ngettext("{n} device nearby", "{n} devices nearby", n).format(n=n)
        self.visible_row.set_subtitle(sub)
        self.visible_row.set_sensitive(st != "stopping")
        self.banner.set_revealed(st == "up" and self.wifi_off)
        self._syncing = True
        self.visible_row.set_active(st in ("starting", "up"))
        self._syncing = False

    # ---------------------------------------------------------- radio

    def _on_visible_toggled(self, row, _pspec):
        if self._syncing:
            return
        if row.get_active():
            self.start_radio()
        else:
            self.stop_all()

    def _spawn(self, argv, on_line, on_exit, on_partial=None):
        try:
            return OwlyProcess(argv, on_line, on_exit, on_partial)
        except GLib.Error as e:
            self.log("app", f"can't run {argv[0]}: {e.message}")
            self.toast(_("Couldn't run owly. Is Owly installed?"))
            return None

    def start_radio(self):
        if self.radio_state != "off":
            return
        self.user_stopped = False
        self.last_error = None
        self.peer_count = 0
        self.radio = self._spawn([OWLY, "radio", "up"], self._on_radio_line, self._on_radio_exit)
        self.radio_state = "starting" if self.radio else "off"
        self._update_status()

    def _on_radio_line(self, _stream, line):
        self.log("radio", line)
        if RE_UP.match(line):
            self.radio_state = "up"
            self._check_wifi()
            self.start_receiver()
            pending, self.after_up = self.after_up, []
            for fn in pending:
                fn()
        elif m := RE_PEERS.match(line):
            peers = m.group(1).strip()
            self.peer_count = 0 if peers == "none" else len(peers.split(", "))
        elif line.startswith("owly: the radio went down: "):
            self.last_error = line.split(": ", 2)[2]
        elif line.startswith("owly: "):
            self.last_error = line[len("owly: "):]
        self._update_status()

    def _check_wifi(self):
        """Owly's exclusive modes take Wi-Fi down, shared mode doesn't: ask NetworkManager."""
        try:
            proc = Gio.Subprocess.new(["nmcli", "-t", "-f", "TYPE,STATE", "device"], Gio.SubprocessFlags.STDOUT_PIPE)
        except GLib.Error:
            return

        def done(p, res):
            try:
                _ok, out, _err = p.communicate_utf8_finish(res)
            except GLib.Error:
                return
            self.wifi_off = "wifi:connected" not in (out or "").split()
            self._update_status()

        proc.communicate_utf8_async(None, None, done)

    def _on_radio_exit(self, code):
        self.log("radio", f"exited (code {code})")
        self.radio = None
        if self.receiver:
            self.receiver.signal(signal.SIGINT)
        unexpected = not self.user_stopped
        self.radio_state = "off" if not self.receiver else "stopping"
        self.after_up = []
        self._update_status()
        if unexpected:
            reason = self.last_error or _("exit code {code}").format(code=code)
            self.toast(_("The radio stopped: {reason}").format(reason=reason), timeout=8)
        self._maybe_finished()

    def start_receiver(self):
        if self.receiver or self.radio_state != "up":
            return
        self.receiver_ready = False
        argv = [OWLY, "receive", "--dir", self.settings["dir"], "--name", self.settings["name"]]
        if self.settings["auto_accept"]:
            argv.append("--accept")
        os.makedirs(self.settings["dir"], exist_ok=True)
        self.receiver = self._spawn(argv, self._on_receiver_line, self._on_receiver_exit, self._on_receiver_partial)

    def _on_receiver_exit(self, code):
        self.log("receive", f"exited (code {code})")
        self.receiver = None
        self.receiver_ready = False
        self._close_request_dialog()
        if self.restart_receiver and self.radio_state == "up":
            self.restart_receiver = False
            self.start_receiver()
        elif self.radio_state == "up" and not self.user_stopped:
            self.toast(_("The receiver stopped (see the log)."), timeout=8)
        if self.radio_state == "stopping" and not self.radio:
            self.radio_state = "off"
        self._update_status()
        self._maybe_finished()

    def stop_all(self):
        if self.radio_state == "off" and not self.receiver:
            self._maybe_finished()
            return
        self.user_stopped = True
        self.radio_state = "stopping"
        self._close_request_dialog()
        self._update_status()
        if self.receiver:
            self.receiver.signal(signal.SIGINT)
        if self.radio:
            self.radio.signal(signal.SIGTERM)
        GLib.timeout_add_seconds(STOP_TIMEOUT_S, self._force_stop)

    def _force_stop(self):
        for p in (self.receiver, self.radio):
            if p:
                self.log("app", "forcing it to stop")
                p.kill()
        return GLib.SOURCE_REMOVE

    def _maybe_finished(self):
        if self.radio or self.receiver:
            return
        self.radio_state = "off"
        self._update_status()
        if self.quitting:
            self.app.quit()

    def _on_close_request(self, _win):
        if self.radio or self.receiver:
            self.quitting = True
            self.set_visible(False)
            self.stop_all()
            return True  # quit once Wi-Fi is given back
        return False

    # ------------------------------------------------------- receiving

    def _on_receiver_line(self, stream, line):
        self.log("receive", line)
        if stream == "out":
            self._on_received(line)
            return
        if line.startswith("receiving as "):
            self.receiver_ready = True
            self._update_status()
        elif m := RE_REQUEST.match(line):
            self.request = {
                "sender": rust_unquote(m.group(1)) or _("A device"),
                "model": rust_unquote(m.group(2)),
                "files": [],
                "urls": [],
                "answered": False,
            }
            if self.settings["auto_accept"]:
                self.toast(_("Receiving from {sender}…").format(sender=self.request["sender"]))
        elif self.request and (m := RE_FILE.match(line)):
            size = int(m.group(3)) if m.group(3) else None
            self.request["files"].append((rust_unquote(m.group(1)), size))
        elif self.request and (m := RE_URL.match(line)):
            self.request["urls"].append(rust_unquote(m.group(1)))
        elif line.strip() == "timed out":
            self._close_request_dialog()
            self.toast(_("Request expired (no answer within 15 s)"))
        elif line == "the request was withdrawn":
            self._close_request_dialog()
            self.toast(_("The sender cancelled"))
        elif line.startswith("transfer failed: "):
            reason = line[len("transfer failed: "):]
            self.toast(_("Receiving failed: {reason}").format(reason=reason), timeout=8)
        elif line.strip() == PROMPT:
            self._ask()

    def _on_receiver_partial(self, _stream, text):
        if text.strip() == PROMPT:
            self.log("receive", text.strip())
            self._ask()
            return True
        return False

    def _request_heading(self):
        r = self.request
        if r["urls"]:
            return _("{sender} wants to send you a link").format(sender=r["sender"])
        n = len(r["files"])
        return ngettext(
            "{sender} wants to send you {n} file", "{sender} wants to send you {n} files", n
        ).format(sender=r["sender"], n=n)

    def _request_summary(self):
        r = self.request
        if r["urls"]:
            return "\n".join(r["urls"])
        names = [n for n, _size in r["files"]]
        total = sum(s for _name, s in r["files"] if s)
        shown = "\n".join(names[:5])
        if len(names) > 5:
            shown += "\n" + _("… and {n} more").format(n=len(names) - 5)
        head = files_label(len(names)) + (f" · {human_size(total)}" if total else "")
        return f"{head}\n\n{shown}"

    def _ask(self):
        if not self.request or self.request["answered"]:
            return
        heading, summary = self._request_heading(), self._request_summary()
        dialog = Adw.AlertDialog.new(heading, summary)
        dialog.add_response("decline", _("Decline"))
        dialog.add_response("accept", _("Accept"))
        dialog.set_response_appearance("accept", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("accept")
        dialog.set_close_response("decline")
        dialog.connect("response", lambda _d, resp: self.answer(resp == "accept"))
        # owly declines by itself after 15 s: never answer after that, or the
        # late answer would be read for the next request.
        self.request_timer = GLib.timeout_add_seconds(14, self._request_expired)
        self.notify(
            "request", heading, summary,
            buttons=((_("Decline"), "app.decline-request"), (_("Accept"), "app.accept-request")),
        )
        if self.selftest:
            GLib.timeout_add(200, lambda: self.answer(True) and False)
        else:
            self.request_dialog = dialog
            self.present()
            dialog.present(self)

    def _request_expired(self):
        self.request_timer = 0
        if self.request:
            self.request["answered"] = True
        self._close_request_dialog()
        return GLib.SOURCE_REMOVE

    def answer(self, accept):
        r = self.request
        if not r or r["answered"] or not self.receiver:
            return False
        r["answered"] = True
        self.receiver.write("y\n" if accept else "n\n")
        self.log("app", "accepted" if accept else "declined")
        self._close_request_dialog()
        if accept:
            self.toast(_("Receiving from {sender}…").format(sender=r["sender"]))
        return True

    def _close_request_dialog(self):
        if self.request_timer:
            GLib.source_remove(self.request_timer)
            self.request_timer = 0
        if self.request_dialog:
            d, self.request_dialog = self.request_dialog, None
            d.force_close()
        self.app.withdraw_notification("request")

    def _on_received(self, line):
        sender = self.request["sender"] if self.request else _("an iPhone")
        is_url = line.startswith('"')
        item = rust_unquote(line) if is_url else line
        self._add_received_row(item, is_url, sender)
        self.incoming.append(item if is_url else os.path.basename(item))
        if not self.incoming_timer:
            self.incoming_timer = GLib.timeout_add(600, self._flush_incoming, sender)

    def _flush_incoming(self, sender):
        self.incoming_timer = 0
        items, self.incoming = self.incoming, []
        title = _("From {sender}").format(sender=sender)
        body = items[0] if len(items) == 1 else files_label(len(items))
        self.toast(_("{title}: {body}").format(title=title, body=body))
        self.notify("received", title, body)
        return GLib.SOURCE_REMOVE

    def _add_received_row(self, item, is_url, sender):
        if self.received_rows == 0:
            self.received_group.remove(self.placeholder)
        self.received_rows += 1
        when = time.strftime("%H:%M")
        if is_url:
            sub = _("Link · {sender} · {time}").format(sender=sender, time=when)
            row = Adw.ActionRow(title=GLib.markup_escape_text(item), subtitle=GLib.markup_escape_text(sub))
            row.add_suffix(self._icon_button("edit-copy-symbolic", _("Copy"), lambda *_a: self._copy(item)))
            row.add_suffix(self._icon_button(
                "web-browser-symbolic", _("Open"),
                lambda *_a: Gtk.UriLauncher.new(item).launch(self, None, None, None),
            ))
        else:
            try:
                size = human_size(os.path.getsize(item))
            except OSError:
                size = ""
            sub = " · ".join(x for x in (size, sender, when) if x)
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(os.path.basename(item)), subtitle=GLib.markup_escape_text(sub)
            )
            gfile = Gio.File.new_for_path(item)
            row.add_suffix(self._icon_button(
                "folder-open-symbolic", _("Show in Folder"),
                lambda *_a: Gtk.FileLauncher.new(gfile).open_containing_folder(self, None, None, None),
            ))
            row.add_suffix(self._icon_button(
                "document-open-symbolic", _("Open"),
                lambda *_a: Gtk.FileLauncher.new(gfile).launch(self, None, None, None),
            ))
        self.received_group.add(row)

    def _icon_button(self, icon, tooltip, cb):
        b = Gtk.Button(icon_name=icon, tooltip_text=tooltip, valign=Gtk.Align.CENTER)
        b.add_css_class("flat")
        b.connect("clicked", cb)
        return b

    def _copy(self, text):
        self.get_clipboard().set_content(
            Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", GLib.Bytes.new(text.encode()))
        )
        self.toast(_("Link copied"))

    # --------------------------------------------------------- sending

    def _on_send_clicked(self, _row):
        Gtk.FileDialog(title=_("Files to Send")).open_multiple(self, None, self._on_files_chosen)

    def _on_files_chosen(self, dialog, res):
        try:
            model = dialog.open_multiple_finish(res)
        except GLib.Error:
            return
        paths = [model.get_item(i).get_path() for i in range(model.get_n_items())]
        self.send_files([p for p in paths if p])

    def _on_drop(self, _target, value, _x, _y):
        paths = [f.get_path() for f in value.get_files() if f.get_path()]
        if paths:
            self.send_files(paths)
        return bool(paths)

    def send_files(self, paths):
        if self.radio_state == "up":
            self._open_browse_dialog(paths)
            return
        self.after_up.append(lambda: self._open_browse_dialog(paths))
        if self.radio_state == "off":
            self.toast(_("Turning the radio on…"))
            self.start_radio()

    def _open_browse_dialog(self, paths):
        n = len(paths)
        title = ngettext("Send {n} File", "Send {n} Files", n).format(n=n)
        dlg = Adw.Dialog(title=title, content_width=440)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for setter in (box.set_margin_top, box.set_margin_bottom, box.set_margin_start, box.set_margin_end):
            setter(12)
        status = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        spinner = Adw.Spinner()
        label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        status.append(spinner)
        status.append(label)
        box.append(status)
        hint = Gtk.Label(
            label=_("On the iPhone: unlocked, AirDrop set to “Everyone for 10 Minutes”."),
            wrap=True, justify=Gtk.Justification.CENTER,
        )
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        box.append(hint)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, visible=False)
        listbox.add_css_class("boxed-list")
        box.append(listbox)
        retry = Gtk.Button(label=_("Search Again"), halign=Gtk.Align.CENTER, visible=False)
        retry.add_css_class("pill")
        box.append(retry)
        view.set_content(box)
        dlg.set_child(view)

        st = {"proc": None, "seen": set(), "closed": False}

        def pick(name):
            if not self.selftest:
                dlg.close()
            self._do_send(name, paths)

        def on_line(stream, line):
            self.log("browse", line)
            m = RE_BROWSE.match(line) if stream == "out" else None
            if not m or m.group(1) in st["seen"]:
                return
            st["seen"].add(m.group(1))
            name = rust_unquote(m.group(2))
            row = Adw.ActionRow(title=GLib.markup_escape_text(name), activatable=True)
            row.add_prefix(Gtk.Image.new_from_icon_name("phone-symbolic"))
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect("activated", lambda *_a: pick(name))
            listbox.append(row)
            listbox.set_visible(True)

        def on_exit(_code):
            st["proc"] = None
            if st["closed"]:
                return
            spinner.set_visible(False)
            label.set_label(_("Choose who to send to:") if st["seen"] else _("No devices found."))
            retry.set_visible(True)

        def start():
            spinner.set_visible(True)
            label.set_label(_("Looking for nearby devices…"))
            retry.set_visible(False)
            st["proc"] = self._spawn(
                [OWLY, "browse", "--seconds", "10", "--name", self.settings["name"]], on_line, on_exit
            )

        def on_closed(_d):
            st["closed"] = True
            if st["proc"]:
                st["proc"].signal(signal.SIGINT)

        retry.connect("clicked", lambda *_a: start())
        dlg.connect("closed", on_closed)
        if self.selftest:
            self._selftest_browse = (st, pick)
        else:
            dlg.present(self)
        start()

    def _do_send(self, name, paths):
        row = Adw.ActionRow(
            title=GLib.markup_escape_text(_("Sending to {name}").format(name=name)),
            subtitle=_("Looking for the iPhone…"),
        )
        bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=110)
        row.add_suffix(bar)
        self.send_group.add(row)
        st = {"outcome": None, "last": None}

        def on_partial(_stream, text):
            m = RE_PROGRESS.match(text.strip())
            if m:
                sent, total = int(m.group(1)), int(m.group(2))
                bar.set_fraction(sent / total if total else 0)
                row.set_subtitle(f"{human_size(sent)} / {human_size(total)}")
                return True
            return False

        def on_line(stream, line):
            self.log("send", line)
            if stream == "out":
                st["outcome"] = line
            elif line.startswith("sending to "):
                row.set_subtitle(_("Waiting for the iPhone to accept…"))
            elif line == "accepted":
                row.set_subtitle(_("Sending…"))
            elif not on_partial(stream, line):
                st["last"] = line

        def on_exit(code):
            self.send_group.remove(row)
            out = st["outcome"] or ""
            if out == "delivered":
                self.toast(_("Sent to {name}").format(name=name))
            elif out == "declined":
                self.toast(_("{name} declined").format(name=name))
            else:
                reason = out[len("failed: "):] if out.startswith("failed: ") else (
                    st["last"] or _("exit code {code}").format(code=code)
                )
                self.toast(_("Sending failed: {reason}").format(reason=reason), timeout=8)
            if self.selftest:
                self._selftest_sent = out

        proc = self._spawn(
            [OWLY, "send", "--to", name, "--name", self.settings["name"], "--", *paths],
            on_line, on_exit, on_partial,
        )
        if not proc:
            self.send_group.remove(row)

    # -------------------------------------------------------- settings

    def _on_auto_toggled(self, row, _pspec):
        self.settings["auto_accept"] = row.get_active()
        save_settings(self.settings)
        self._restart_receiver_if_running()

    def _on_name_applied(self, row):
        name = row.get_text().strip()
        if not name:
            row.set_text(self.settings["name"])
            return
        self.settings["name"] = name
        save_settings(self.settings)
        self.toast(_("Name saved"))
        self._restart_receiver_if_running()

    def _on_choose_dir(self, _btn):
        d = Gtk.FileDialog(title=_("Download folder"), initial_folder=Gio.File.new_for_path(self.settings["dir"]))
        d.select_folder(self, None, self._on_dir_chosen)

    def _on_dir_chosen(self, dialog, res):
        try:
            path = dialog.select_folder_finish(res).get_path()
        except GLib.Error:
            return
        if path:
            self.settings["dir"] = path
            self.dir_row.set_subtitle(path)
            save_settings(self.settings)
            self._restart_receiver_if_running()

    def _restart_receiver_if_running(self):
        if self.receiver and self.radio_state == "up":
            self.restart_receiver = True
            self.receiver.signal(signal.SIGINT)


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


class App(Adw.Application):
    def __init__(self, selftest=False):
        flags = Gio.ApplicationFlags.NON_UNIQUE if selftest else Gio.ApplicationFlags.DEFAULT_FLAGS
        super().__init__(application_id=APP_ID, flags=flags)
        self.selftest = selftest
        self.selftest_ok = False
        self.win = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        for name, accept in (("accept-request", True), ("decline-request", False)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, yes=accept: self.win and self.win.answer(yes))
            self.add_action(action)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_a: self.win and self.win.close())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        # Logout or kill: give Wi-Fi back cleanly.
        try:
            gi.require_version("GLibUnix", "2.0")
            from gi.repository import GLibUnix

            add_signal = GLibUnix.signal_add
        except (ImportError, ValueError):
            add_signal = GLib.unix_signal_add
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            add_signal(GLib.PRIORITY_DEFAULT, sig, self._on_signal)

    def _on_signal(self):
        if self.win:
            self.win.close()
        else:
            self.quit()
        return GLib.SOURCE_CONTINUE

    def do_activate(self):
        if not self.win:
            self.win = Window(self, self.selftest)
            if self.selftest:
                self.hold()
                GLib.idle_add(run_selftest, self.win)
                return
        self.win.present()


# --------------------------------------------------------------------------
# Self-test, against a fake owly (see tests/)
# --------------------------------------------------------------------------


def run_selftest(win):
    """Radio up -> request -> accept -> file received -> browse -> send -> stop."""
    checks = {}
    app = win.app
    deadline = time.monotonic() + 20
    win.settings["dir"] = tempfile.mkdtemp(prefix="owly-drop-test-")

    def step():
        if time.monotonic() > deadline:
            return finish("timed out")
        if "up" not in checks:
            if win.radio_state == "up" and win.receiver_ready:
                checks["up"] = True
            return True
        if "received" not in checks:
            if win.received_rows:
                checks["received"] = True
                win.send_files([os.path.realpath(__file__)])
            return True
        if "browse" not in checks:
            sb = getattr(win, "_selftest_browse", None)
            if sb and sb[0]["seen"] and sb[0]["proc"] is None:
                checks["browse"] = True
                sb[1]("Alice's iPhone")
            return True
        if "sent" not in checks:
            if getattr(win, "_selftest_sent", None):
                checks["sent"] = win._selftest_sent == "delivered"
                win.stop_all()
            return True
        if win.radio is None and win.receiver is None:
            checks["stopped"] = win.radio_state == "off"
            return finish(None)
        return True

    def finish(err):
        shutil.rmtree(win.settings["dir"], ignore_errors=True)
        ok = err is None and len(checks) == 5 and all(checks.values())
        print("SELFTEST", "OK" if ok else "FAILED", checks, err or "")
        app.selftest_ok = ok
        app.release()
        app.quit()
        return False

    win.start_radio()
    GLib.timeout_add(100, step)
    return False


def parser_selftest():
    assert rust_unquote('"Bob\'s \\"iPhone\\""') == 'Bob\'s "iPhone"'
    assert rust_unquote('Some("Mac\\u{2019}s")') == "Mac\u2019s"
    assert rust_unquote("None") == ""
    m = RE_REQUEST.match('"Alice\'s iPhone" ("iPhone") wants to send:')
    assert m and rust_unquote(m.group(1)) == "Alice's iPhone"
    m = RE_REQUEST.match('Some("A (b)") (Some("iPhone15,2")) wants to send:')
    assert m and rust_unquote(m.group(1)) == "A (b)"
    m = RE_FILE.match('  "IMG_0001.HEIC" public.heic 2345678 bytes')
    assert m and m.group(3) == "2345678"
    m = RE_FILE.match('  "a b.jpg" public.jpeg ')
    assert m and m.group(3) is None
    m = RE_BROWSE.match('a1b2c3d4e5f6   "Alice\'s iPhone" ([fe80::1%awdl0]:8770)')
    assert m and rust_unquote(m.group(2)) == "Alice's iPhone"
    assert RE_UP.match("awdl0 is up: fe80::1%awdl0 (02:00:00:00:00:01). Ctrl-C takes it down.")
    assert RE_PROGRESS.match("1024 / 2048 bytes")
    for po in sorted(os.listdir(os.path.join(HERE, "po"))):
        entries = parse_po(os.path.join(HERE, "po", po))
        assert entries, po
        print(f"{po}: {len(entries)} translations")
    fr = parse_po(os.path.join(HERE, "po", "fr.po"))
    assert fr[("{n} file", "{n} files")] == ["{n} fichier", "{n} fichiers"]
    print("parser OK")


def main():
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    load_translations()
    if "--selftest" in sys.argv:
        parser_selftest()
        app = App(selftest=True)
        app.run([sys.argv[0]])
        return 0 if app.selftest_ok else 1
    if "--version" in sys.argv:
        print(f"Owly Drop {VERSION}")
        return 0
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
