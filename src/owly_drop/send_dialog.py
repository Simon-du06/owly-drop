# SPDX-License-Identifier: MIT
"""Choosing which nearby iPhone to send files to."""

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, GObject, Gtk

from . import RESOURCE_PREFIX
from .backend import Browser, OwlyError


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/send-dialog.ui")
class SendDialog(Adw.Dialog):
    """Browses for receivers; "chosen" gives the one picked, then the dialog closes."""

    __gtype_name__ = "OwlyDropSendDialog"
    __gsignals__ = {"chosen": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    spinner = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    device_list = Gtk.Template.Child()
    retry_button = Gtk.Template.Child()

    def __init__(self, file_count: int, browser: Browser) -> None:
        super().__init__()
        self.set_title(ngettext("Send {n} File", "Send {n} Files", file_count).format(n=file_count))
        self.browser = browser
        browser.connect("found", self._on_found)
        browser.connect("finished", self._on_finished)
        self.connect("closed", lambda _dialog: browser.stop())
        self._search()

    def _search(self) -> None:
        self.spinner.set_visible(True)
        self.retry_button.set_visible(False)
        self.status_label.set_label(_("Looking for nearby devices…"))
        try:
            self.browser.start()
        except OwlyError:
            self.spinner.set_visible(False)
            self.status_label.set_label(_("Couldn't run owly. Is Owly installed?"))

    def _on_found(self, _browser: Browser, _service_id: str, name: str) -> None:
        row = Adw.ActionRow(title=name, use_markup=False, activatable=True)
        row.add_prefix(Gtk.Image.new_from_icon_name("phone-symbolic"))
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda _row: self._choose(name))
        self.device_list.append(row)
        self.device_list.set_visible(True)

    def _on_finished(self, browser: Browser) -> None:
        self.spinner.set_visible(False)
        self.retry_button.set_visible(True)
        if browser.found:
            self.status_label.set_label(_("Choose who to send to:"))
        else:
            self.status_label.set_label(_("No devices found."))

    def _choose(self, name: str) -> None:
        self.emit("chosen", name)
        self.close()

    @Gtk.Template.Callback()
    def on_retry(self, _button: Gtk.Button) -> None:
        self.device_list.remove_all()
        self.device_list.set_visible(False)
        self._search()
