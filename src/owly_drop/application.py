# SPDX-License-Identifier: MIT
"""The application: one window, a Session, and the app-wide actions."""

import signal
from gettext import gettext as _

import gi
from gi.repository import Adw, Gio, GLib, Gtk

from . import APP_ID, RESOURCE_PREFIX
from .backend import Session
from .settings import Settings
from .window import Window


class Application(Adw.Application):
    def __init__(self, version: str) -> None:
        super().__init__(
            application_id=APP_ID,
            resource_base_path=RESOURCE_PREFIX,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.version = version
        self.settings: Settings | None = None
        self.session: Session | None = None
        self.add_main_option(
            "version",
            ord("v"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Show the version and quit"),
            None,
        )

    def do_handle_local_options(self, options: GLib.VariantDict) -> int:
        if options.contains("version"):
            print(f"Owly Drop {self.version}")
            return 0
        return -1  # carry on starting

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.settings = Settings()
        self.session = Session()
        self.settings.connect("changed", lambda *_args: self._configure_session())
        self._configure_session()

        self._add_action("quit", self._on_quit, ["<primary>q"])
        self._add_action("about", self._on_about)
        self._add_action("accept-request", lambda *_args: self._answer_request(True))
        self._add_action("decline-request", lambda *_args: self._answer_request(False))
        self.set_accels_for_action("win.send-files", ["<primary>o"])
        self._handle_unix_signals()

    def do_activate(self) -> None:
        window = self._window() or Window(self, self.session, self.settings)
        window.present()

    def _window(self) -> Window | None:
        """The main window, even while it is hidden and giving Wi-Fi back."""
        return next((w for w in self.get_windows() if isinstance(w, Window)), None)

    def _configure_session(self) -> None:
        settings = self.settings
        self.session.configure(settings.device_name, settings.download_folder, settings.auto_accept)

    def _add_action(self, name: str, callback, accels=None) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accels:
            self.set_accels_for_action(f"app.{name}", accels)

    def _answer_request(self, accept: bool) -> None:
        window = self._window()
        if window:
            window.answer_request(accept)

    def _on_quit(self, *_args) -> None:
        window = self._window()
        if window:
            window.close()  # gives Wi-Fi back first, see Window.do_close_request
        else:
            self.quit()

    def _handle_unix_signals(self) -> None:
        """Logging out or `kill`: give Wi-Fi back before quitting, as closing does."""
        try:
            gi.require_version("GLibUnix", "2.0")
            from gi.repository import GLibUnix

            add_signal = GLibUnix.signal_add
        except (ImportError, ValueError):  # GLib older than 2.80
            add_signal = GLib.unix_signal_add
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            add_signal(GLib.PRIORITY_DEFAULT, signum, self._on_unix_signal)

    def _on_unix_signal(self) -> bool:
        self._on_quit()
        return GLib.SOURCE_CONTINUE

    def _on_about(self, *_args) -> None:
        about = Adw.AboutDialog(
            application_name="Owly Drop",
            application_icon=APP_ID,
            developer_name="Simon Puccio",
            version=self.version,
            website="https://github.com/Simon-du06/owly-drop",
            issue_url="https://github.com/Simon-du06/owly-drop/issues",
            license_type=Gtk.License.MIT_X11,
            copyright="© 2026 Simon Puccio",
            # Translators: Replace "translator-credits" with your name, one per line.
            translator_credits=_("translator-credits"),
        )
        about.add_credit_section(
            _("Built on"),
            [
                "Owly https://github.com/t4t5/owly",
                "OWL https://github.com/seemoo-lab/owl",
                "OpenDrop https://github.com/seemoo-lab/opendrop",
            ],
        )
        about.present(self._window())
