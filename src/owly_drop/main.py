# SPDX-License-Identifier: MIT
"""The entry point the owly-drop launcher calls."""

import sys

from .application import Application


def main(version: str) -> int:
    return Application(version).run(sys.argv)
