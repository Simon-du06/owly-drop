# SPDX-License-Identifier: MIT
"""A received file or link in the "Received" list."""

import os
import time
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import RESOURCE_PREFIX
from .formatting import human_size


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/received-row.ui")
class ReceivedRow(Adw.ActionRow):
    __gtype_name__ = "OwlyDropReceivedRow"

    copy_button = Gtk.Template.Child()
    folder_button = Gtk.Template.Child()

    def __init__(self, item: str, is_url: bool, sender: str) -> None:
        super().__init__()
        self.item = item
        self.is_url = is_url
        when = time.strftime("%H:%M")
        # Received items are named by the sender: never read them as markup.
        self.set_use_markup(False)
        if is_url:
            self.set_title(item)
            self.set_subtitle(_("Link · {sender} · {time}").format(sender=sender, time=when))
            self.copy_button.set_visible(True)
        else:
            self.set_title(os.path.basename(item))
            try:
                size = human_size(os.path.getsize(item))
            except OSError:
                size = ""
            self.set_subtitle(" · ".join(part for part in (size, sender, when) if part))
            self.folder_button.set_visible(True)

    @Gtk.Template.Callback()
    def on_open(self, _button: Gtk.Button) -> None:
        window = self.get_root()
        if self.is_url:
            Gtk.UriLauncher.new(self.item).launch(window, None, None, None)
        else:
            Gtk.FileLauncher.new(Gio.File.new_for_path(self.item)).launch(window, None, None, None)

    @Gtk.Template.Callback()
    def on_show_in_folder(self, _button: Gtk.Button) -> None:
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(self.item))
        launcher.open_containing_folder(self.get_root(), None, None, None)

    @Gtk.Template.Callback()
    def on_copy(self, _button: Gtk.Button) -> None:
        provider = Gdk.ContentProvider.new_for_bytes(
            "text/plain;charset=utf-8", GLib.Bytes.new(self.item.encode())
        )
        self.get_clipboard().set_content(provider)
        self.activate_action("win.toast", GLib.Variant.new_string(_("Link copied")))
