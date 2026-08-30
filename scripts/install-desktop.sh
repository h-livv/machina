#!/usr/bin/env bash
# Install a KDE/GNOME app-menu launcher for this machine only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA/applications"
HICOLOR="$DATA/icons/hicolor"
SVG="$ROOT/src/machina/assets/machina.svg"

mkdir -p "$APP_DIR" "$HICOLOR/scalable/apps" "$DATA/pixmaps"
install -m 644 "$SVG" "$HICOLOR/scalable/apps/machina.svg"

if command -v magick >/dev/null 2>&1; then
  for size in 16 22 24 32 48 64 128 256; do
    dest="$HICOLOR/${size}x${size}/apps"
    mkdir -p "$dest"
    magick -background none -density 384 "$SVG" -resize "${size}x${size}" -depth 8 "PNG32:$dest/machina.png"
  done
  install -m 644 "$HICOLOR/128x128/apps/machina.png" "$DATA/pixmaps/machina.png"
fi

install -m 644 "$ROOT/packaging/machina.desktop" "$APP_DIR/machina.desktop"
chmod +x "$ROOT/scripts/machina"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f "$HICOLOR" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 >/dev/null 2>&1 || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 >/dev/null 2>&1 || true
fi

echo "Installed $APP_DIR/machina.desktop"
echo "Machina is in the app menu. Unpin the blank icon, then pin Machina again from the launcher."
