# SPDX-License-Identifier: MIT
"""The main window: shows the Session and drives it."""

import time
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import RESOURCE_PREFIX
from .backend import Browser, OwlyError, Request, Session, Transfer
from .backend.session import OFF, STARTING, STOPPING, UP
from .formatting import files_label
from .received_row import ReceivedRow
from .request_dialog import RequestDialog, request_body, request_heading
from .send_dialog import SendDialog
from .settings import Settings
from .transfer_row import TransferRow

MAX_LOG_LINES = 600
NOTIFICATION_REQUEST = "request"
NOTIFICATION_RECEIVED = "received"


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/window.ui")
class Window(Adw.ApplicationWindow):
    __gtype_name__ = "OwlyDropWindow"

    banner = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    visible_row = Gtk.Template.Child()
    auto_accept_row = Gtk.Template.Child()
    send_group = Gtk.Template.Child()
    received_group = Gtk.Template.Child()
    placeholder_row = Gtk.Template.Child()
    name_row = Gtk.Template.Child()
    folder_row = Gtk.Template.Child()
    log_view = Gtk.Template.Child()

    def __init__(self, application: Adw.Application, session: Session, settings: Settings):
        super().__init__(application=application)
        self.session = session
        self.settings = settings
        self.request: Request | None = None
        self._syncing = False
        self._quitting = False
        self._received_batch: list[str] = []
        self._received_timer = 0

        self._add_actions()
        settings.bind("auto-accept", self.auto_accept_row, "active", Gio.SettingsBindFlags.DEFAULT)
        settings.connect("changed", self._on_settings_changed)
        self._on_settings_changed(settings, None)

        for prop in ("state", "receiving", "peer-count", "wifi-off"):
            session.connect(f"notify::{prop}", self._sync_status)
        session.connect("log", self._on_log)
        session.connect("request", self._on_request)
        session.connect("incoming", self._on_incoming)
        session.connect("received", self._on_received)
        session.connect("failed", self._on_failed)

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        self.add_controller(drop_target)
        self._sync_status()

    def _add_actions(self) -> None:
        send = Gio.SimpleAction.new("send-files", None)
        send.connect("activate", lambda *_args: self._choose_files())
        self.add_action(send)
        toast = Gio.SimpleAction.new("toast", GLib.VariantType.new("s"))
        toast.connect("activate", lambda _action, text: self.toast(text.get_string()))
        self.add_action(toast)

    # ------------------------------------------------------------ helpers

    def toast(self, text: str, timeout: int = 4) -> None:
        toast = Adw.Toast.new(text)
        toast.set_use_markup(False)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    def _notify(self, notification_id: str, title: str, body: str, buttons=()) -> None:
        """A desktop notification, when the window isn't the one being looked at."""
        if self.is_active():
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        for label, action in buttons:
            notification.add_button(label, action)
        if buttons:
            notification.set_priority(Gio.NotificationPriority.HIGH)
        self.get_application().send_notification(notification_id, notification)

    def _on_log(self, _source_object, source: str, line: str) -> None:
        buffer = self.log_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), f"{time.strftime('%H:%M:%S')} [{source}] {line}\n")
        excess = buffer.get_line_count() - MAX_LOG_LINES
        if excess > 0:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(excess)[1])

    # ------------------------------------------------------------- status

    def _sync_status(self, *_args) -> None:
        session = self.session
        if session.state == OFF:
            subtitle = _("Off")
        elif session.state == STARTING:
            subtitle = _("Starting the radio…")
        elif session.state == STOPPING:
            subtitle = _("Stopping…")
        elif not session.receiving:
            subtitle = _("Radio up, starting the receiver…")
        else:
            subtitle = _("Visible: on the iPhone, tap Share, then AirDrop")
            if session.peer_count:
                count = session.peer_count
                nearby = ngettext("{n} device nearby", "{n} devices nearby", count)
                subtitle += " · " + nearby.format(n=count)
        self.visible_row.set_subtitle(subtitle)
        self.visible_row.set_sensitive(session.state != STOPPING)
        self.banner.set_revealed(session.state == UP and session.wifi_off)
        self._syncing = True
        self.visible_row.set_active(session.state in (STARTING, UP))
        self._syncing = False

    @Gtk.Template.Callback()
    def on_visible_changed(self, row: Adw.SwitchRow, _pspec) -> None:
        if self._syncing:
            return
        if row.get_active():
            try:
                self.session.start()
            except OwlyError:
                self.toast(_("Couldn't run owly. Is Owly installed?"))
            self._sync_status()
        else:
            self.session.stop()

    def _on_failed(self, _session: Session, kind: str, detail: str) -> None:
        reason = detail or _("unknown error")
        if kind == "radio":
            self.toast(_("The radio stopped: {reason}").format(reason=reason), timeout=8)
        elif kind == "receiver":
            self.toast(_("The receiver stopped (see the log)."), timeout=8)
        elif kind == "transfer":
            self.toast(_("Receiving failed: {reason}").format(reason=reason), timeout=8)

    # ---------------------------------------------------------- receiving

    def _on_request(self, _session: Session, request: Request) -> None:
        self.request = request
        request.connect("closed", self._on_request_closed)
        self._notify(
            NOTIFICATION_REQUEST,
            request_heading(request),
            request_body(request),
            buttons=((_("Decline"), "app.decline-request"), (_("Accept"), "app.accept-request")),
        )
        self.present()
        RequestDialog(request).present(self)

    def _on_request_closed(self, request: Request, reason: str) -> None:
        self.get_application().withdraw_notification(NOTIFICATION_REQUEST)
        if request is self.request:
            self.request = None
        if reason == "accepted":
            self.toast(_("Receiving from {sender}…").format(sender=request.sender))
        elif reason == "expired":
            self.toast(_("Request expired (no answer within 15 s)"))
        elif reason == "withdrawn":
            self.toast(_("The sender cancelled"))

    def answer_request(self, accept: bool) -> None:
        """For the Accept and Decline buttons of the notification."""
        if self.request:
            if accept:
                self.request.accept()
            else:
                self.request.decline()

    def _on_incoming(self, _session: Session, sender: str) -> None:
        self.toast(_("Receiving from {sender}…").format(sender=sender))

    def _on_received(self, _session: Session, sender: str, item: str, is_url: bool) -> None:
        sender = sender or _("an iPhone")
        self.placeholder_row.set_visible(False)
        row = ReceivedRow(item, is_url, sender)
        self.received_group.add(row)
        self._received_batch.append(row.get_title())
        # Several files of one request arrive together: say so once.
        if not self._received_timer:
            self._received_timer = GLib.timeout_add(600, self._report_received, sender)

    def _report_received(self, sender: str) -> bool:
        self._received_timer = 0
        items, self._received_batch = self._received_batch, []
        title = _("From {sender}").format(sender=sender)
        body = items[0] if len(items) == 1 else files_label(len(items))
        self.toast(_("{title}: {body}").format(title=title, body=body))
        self._notify(NOTIFICATION_RECEIVED, title, body)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------ sending

    def _choose_files(self) -> None:
        dialog = Gtk.FileDialog(title=_("Files to Send"))
        dialog.open_multiple(self, None, self._on_files_chosen)

    def _on_files_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return  # cancelled
        paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
        self.send_files([path for path in paths if path])

    def _on_drop(self, _target: Gtk.DropTarget, value: Gdk.FileList, _x, _y) -> bool:
        paths = [f.get_path() for f in value.get_files() if f.get_path()]
        if paths:
            self.send_files(paths)
        return bool(paths)

    def send_files(self, paths: list[str]) -> None:
        if self.session.state == OFF:
            self.toast(_("Turning the radio on…"))
        try:
            self.session.when_up(lambda: self._pick_receiver(paths))
        except OwlyError:
            self.toast(_("Couldn't run owly. Is Owly installed?"))

    def _pick_receiver(self, paths: list[str]) -> None:
        browser = Browser(self.settings.device_name, owly=self.session.owly)
        browser.connect("log", self._on_log)
        dialog = SendDialog(len(paths), browser)
        dialog.connect("chosen", lambda _dialog, name: self._send(name, paths))
        dialog.present(self)

    def _send(self, receiver: str, paths: list[str]) -> None:
        transfer = Transfer(receiver, paths, self.settings.device_name, owly=self.session.owly)
        transfer.connect("log", self._on_log)
        row = TransferRow(transfer)
        row.connect("done", self._on_transfer_done)
        self.send_group.add(row)
        try:
            transfer.start()
        except OwlyError:
            self.send_group.remove(row)
            self.toast(_("Couldn't run owly. Is Owly installed?"))

    def _on_transfer_done(self, row: TransferRow, outcome: str, reason: str) -> None:
        self.send_group.remove(row)
        name = row.transfer.receiver
        if outcome == "delivered":
            self.toast(_("Sent to {name}").format(name=name))
        elif outcome == "declined":
            self.toast(_("{name} declined").format(name=name))
        elif outcome == "failed":
            reason = reason or _("unknown error")
            self.toast(_("Sending failed: {reason}").format(reason=reason), timeout=8)

    # ----------------------------------------------------------- settings

    def _on_settings_changed(self, settings: Settings, _key) -> None:
        self.name_row.set_text(settings.device_name)
        self.folder_row.set_subtitle(settings.download_folder)

    @Gtk.Template.Callback()
    def on_name_applied(self, row: Adw.EntryRow) -> None:
        name = row.get_text().strip()
        self.settings.device_name = name  # empty goes back to the default
        row.set_text(self.settings.device_name)
        self.toast(_("Name saved"))

    @Gtk.Template.Callback()
    def on_choose_folder(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(
            title=_("Download Folder"),
            initial_folder=Gio.File.new_for_path(self.settings.download_folder),
        )
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # cancelled
        if folder.get_path():
            self.settings.download_folder = folder.get_path()

    # ------------------------------------------------------------ closing

    def do_close_request(self) -> bool:
        """Closing while visible: hide, give Wi-Fi back, then quit."""
        if not self.session.busy:
            return False
        self.set_visible(False)
        if not self._quitting:
            self._quitting = True
            self.session.connect("stopped", lambda _session: self.get_application().quit())
        self.session.stop()
        return True
