# SPDX-License-Identifier: MIT
"""Asking whether to accept what an iPhone wants to send."""

from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw

from .backend import Request
from .formatting import files_label, human_size

MAX_LISTED_FILES = 5


def request_heading(request: Request) -> str:
    if request.urls:
        return _("{sender} wants to send you a link").format(sender=request.sender)
    count = len(request.files)
    return ngettext(
        "{sender} wants to send you {n} file", "{sender} wants to send you {n} files", count
    ).format(sender=request.sender, n=count)


def request_body(request: Request) -> str:
    if request.urls:
        return "\n".join(request.urls)
    names = [f.name for f in request.files]
    listed = "\n".join(names[:MAX_LISTED_FILES])
    if len(names) > MAX_LISTED_FILES:
        listed += "\n" + _("… and {n} more").format(n=len(names) - MAX_LISTED_FILES)
    summary = files_label(len(names))
    if request.total_size:
        summary += f" · {human_size(request.total_size)}"
    return f"{summary}\n\n{listed}"


class RequestDialog(Adw.AlertDialog):
    """Accept / Decline for one Request; closes by itself when the request does."""

    __gtype_name__ = "OwlyDropRequestDialog"

    def __init__(self, request: Request) -> None:
        super().__init__(heading=request_heading(request), body=request_body(request))
        self.request = request
        self.add_response("decline", _("_Decline"))
        self.add_response("accept", _("_Accept"))
        self.set_response_appearance("accept", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("accept")
        self.set_close_response("decline")
        self.connect("response", self._on_response)
        self._closed_handler = request.connect("closed", self._on_request_closed)

    def _on_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "accept":
            self.request.accept()
        else:
            self.request.decline()

    def _on_request_closed(self, request: Request, _reason: str) -> None:
        request.disconnect(self._closed_handler)
        self.force_close()
