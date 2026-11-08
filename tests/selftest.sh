#!/usr/bin/env bash
# Runs Owly Drop's checks without Wi-Fi or an iPhone: the translations, the
# output parser, then the whole app against tests/fake-owly (radio up, accept a
# file, browse, send, radio down). The app's window isn't shown, but GTK still
# needs a display (run it from a desktop session, or under xvfb-run).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -I tests/check_translations.py

config=$(mktemp -d)
trap 'rm -rf "$config"' EXIT
OWLY_BIN="$PWD/tests/fake-owly" XDG_CONFIG_HOME="$config" LANGUAGE=en \
  python3 -I owly_drop.py --selftest 2>&1 | grep -v '^  \['
exit "${PIPESTATUS[0]}"
