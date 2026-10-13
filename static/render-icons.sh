#!/bin/bash
#
# Draws PSells' app icons, the PNGs beside this script, from icon.svg and
# icon-maskable.svg, which frame the monogram in logo.png. Run it again
# after changing either SVG or the logo:
#
#     static/render-icons.sh
#
# On the Mac: Google Chrome draws each SVG at 512 pixels, headless, and
# macOS's sips scales the smaller sizes down from that. The PNGs are
# committed, so nothing here runs in a build.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

[ -x "$CHROME" ] || { echo "render-icons.sh: no Chrome at $CHROME" >&2; exit 1; }

draw() {
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
        --window-size=512,512 --screenshot="$2" "file://$DIR/$1" > /dev/null 2>&1
    [ "$(sips -g pixelWidth "$2" | awk '/pixelWidth/ {print $2}')" = 512 ] ||
        { echo "render-icons.sh: $2 is not 512 pixels wide" >&2; exit 1; }
}

draw icon.svg "$DIR/icon-512.png"
draw icon-maskable.svg "$DIR/icon-maskable-512.png"
sips -z 192 192 "$DIR/icon-512.png" --out "$DIR/icon-192.png" > /dev/null
sips -z 180 180 "$DIR/icon-512.png" --out "$DIR/apple-touch-icon.png" > /dev/null

for png in icon-512.png icon-maskable-512.png icon-192.png apple-touch-icon.png; do
    echo "$png $(sips -g pixelWidth -g pixelHeight "$DIR/$png" | awk '/pixel/ {printf "%s ", $2}')"
done
