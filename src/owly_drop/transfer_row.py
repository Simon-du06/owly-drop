# SPDX-License-Identifier: MIT
"""A file transfer to an iPhone, with its progress, in the "Send" group."""

from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk

from . import RESOURCE_PREFIX
from .backend import Transfer
from .backend.transfer import CONNECTING, SENDING, WAITING
from .formatting import human_size


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/transfer-row.ui")
class TransferRow(Adw.ActionRow):
    """Shows a Transfer until it ends; "done" then says how, for the window to report."""

    __gtype_name__ = "OwlyDropTransferRow"
    __gsignals__ = {"done": (GObject.SignalFlags.RUN_FIRST, None, (str, str))}

    progress_bar = Gtk.Template.Child()

    def __init__(self, transfer: Transfer) -> None:
        super().__init__()
        self.transfer = transfer
        self.set_use_markup(False)
        self.set_title(_("Sending to {name}").format(name=transfer.receiver))
        transfer.connect("status", self._on_status)
        transfer.connect("progress", self._on_progress)
        transfer.connect("finished", self._on_finished)

    def _on_status(self, _transfer: Transfer, status: str) -> None:
        subtitles = {
            CONNECTING: _("Looking for the iPhone…"),
            WAITING: _("Waiting for the iPhone to accept…"),
            SENDING: _("Sending…"),
        }
        self.set_subtitle(subtitles.get(status, ""))
        if status != SENDING:
            self.progress_bar.pulse()

    def _on_progress(self, _transfer: Transfer, sent: int, total: int) -> None:
        self.progress_bar.set_fraction(sent / total if total else 0)
        self.set_subtitle(f"{human_size(sent)} / {human_size(total)}")

    def _on_finished(self, _transfer: Transfer, outcome: str, reason: str) -> None:
        self.emit("done", outcome, reason)

    @Gtk.Template.Callback()
    def on_cancel(self, _button: Gtk.Button) -> None:
        self.transfer.cancel()
