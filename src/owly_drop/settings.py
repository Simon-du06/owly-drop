# SPDX-License-Identifier: MIT
"""The app's GSettings, with the defaults that depend on the user."""

import os
from gettext import gettext as _

from gi.repository import Gio, GLib

from . import APP_ID


def default_device_name() -> str:
    real_name = GLib.get_real_name()
    if real_name and real_name != "Unknown":
        first = real_name.split()[0]
        # Translators: the default name iPhones see for this computer.
        return _("{name}'s PC").format(name=first[:1].upper() + first[1:])
    return GLib.get_host_name()


def default_download_folder() -> str:
    folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    return folder or os.path.expanduser("~/Downloads")


class Settings(Gio.Settings):
    """io.github.Simon_du06.OwlyDrop, where an empty string means the default."""

    def __init__(self) -> None:
        source = Gio.SettingsSchemaSource.get_default()
        if not source or not source.lookup(APP_ID, True):
            # Gio.Settings would abort the whole process instead.
            raise RuntimeError(f"The GSettings schema {APP_ID} isn't installed.")
        super().__init__(schema_id=APP_ID)

    @property
    def device_name(self) -> str:
        return self.get_string("device-name") or default_device_name()

    @device_name.setter
    def device_name(self, value: str) -> None:
        value = value.strip()
        self.set_string("device-name", "" if value == default_device_name() else value)

    @property
    def download_folder(self) -> str:
        return self.get_string("download-folder") or default_download_folder()

    @download_folder.setter
    def download_folder(self, value: str) -> None:
        self.set_string("download-folder", "" if value == default_download_folder() else value)

    @property
    def auto_accept(self) -> bool:
        return self.get_boolean("auto-accept")
