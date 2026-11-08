# SPDX-License-Identifier: MIT
"""Sizes and counts, as the user reads them."""

import locale
from gettext import gettext as _
from gettext import ngettext


def human_size(size: int | None) -> str:
    if size is None:
        return ""
    units = (_("B"), _("KB"), _("MB"), _("GB"))
    value = float(size)
    for i, unit in enumerate(units):
        if value < 1024 or i == len(units) - 1:
            number = f"{value:.0f}" if i == 0 else locale.format_string("%.1f", value)
            # Translators: a file size, such as "2.3 MB".
            return _("{number} {unit}").format(number=number, unit=unit)
        value /= 1024
    return ""


def files_label(count: int) -> str:
    return ngettext("{n} file", "{n} files", count).format(n=count)
