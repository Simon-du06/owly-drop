#!/usr/bin/env bash
# Installs Owly Drop for the current user, in ~/.local (no sudo needed).
#   ./install.sh               install or update
#   ./install.sh --uninstall   remove it (your settings in ~/.config/owly-drop stay)
#   PREFIX=/usr/local sudo -E ./install.sh   install for every user instead
set -euo pipefail

APP_ID=io.github.Simon_du06.OwlyDrop
SRC="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
SHARE="$PREFIX/share"
LIB="$SHARE/owly-drop"
BIN="$PREFIX/bin/owly-drop"
DESKTOP="$SHARE/applications/$APP_ID.desktop"
ICON="$SHARE/icons/hicolor/scalable/apps/$APP_ID.svg"

refresh() {
  update-desktop-database -q "$SHARE/applications" 2>/dev/null || true
  gtk-update-icon-cache -q -t "$SHARE/icons/hicolor" 2>/dev/null || true
}

if [ "${1:-}" = --uninstall ]; then
  rm -rf "$LIB"
  rm -f "$BIN" "$DESKTOP" "$ICON"
  refresh
  echo "Owly Drop removed."
  exit 0
fi

if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw' 2>/dev/null; then
  echo "Owly Drop needs GTK 4 and libadwaita (1.6 or newer) for Python." >&2
  echo "On Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" >&2
  exit 1
fi
if ! command -v owly >/dev/null; then
  echo "Note: owly isn't installed yet. Owly Drop needs it: https://github.com/t4t5/owly" >&2
fi

install -Dm755 "$SRC/owly_drop.py" "$LIB/owly_drop.py"
install -d "$LIB/po"
install -m644 "$SRC"/po/*.po "$LIB/po/"
install -d "$(dirname "$BIN")"
ln -sf "$LIB/owly_drop.py" "$BIN"
install -Dm644 "$SRC/data/$APP_ID.svg" "$ICON"
install -d "$(dirname "$DESKTOP")"
sed "s|@EXEC@|$BIN|" "$SRC/data/$APP_ID.desktop.in" > "$DESKTOP"
refresh

echo "Owly Drop installed. Open it from your app grid, or run: owly-drop"
