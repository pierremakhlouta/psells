"""Tests for PSells' app icons in static/, drawn by static/render-icons.sh
from icon.svg and icon-maskable.svg, which frame the monogram in logo.png.

A phone asks for each size by name, so each must be there, a PNG, at exactly
its size; the maskable icon must be its own drawing, not a copy of the other.
"""

import os
import struct

import psells


STATIC = os.path.join(psells.PROJECT_DIR, "static")

SIZES = {
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-512.png": 512,
}


def png_size(path):
    """The width and height in a PNG's header, read without a library."""
    with open(path, "rb") as file:
        header = file.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", path
    assert header[12:16] == b"IHDR", path
    return struct.unpack(">II", header[16:24])


def test_every_icon_is_a_png_of_its_size():
    for name, size in SIZES.items():
        assert png_size(os.path.join(STATIC, name)) == (size, size), name


def test_the_maskable_icon_is_its_own_drawing():
    def read(name):
        with open(os.path.join(STATIC, name), "rb") as file:
            return file.read()

    assert read("icon-maskable-512.png") != read("icon-512.png")
    # Framed wider, so the monogram stays inside the safe zone: its farthest
    # corner, 289 from its middle, within 40% of the width.
    maskable = read("icon-maskable.svg").decode()
    assert 'viewBox="158.5 47.5 760 760"' in maskable
    assert 289 <= 0.4 * 760
    # Both from the logo, with the word under the monogram covered.
    for name in ("icon.svg", "icon-maskable.svg"):
        svg = read(name).decode()
        assert '<image href="logo.png"' in svg, name
        assert '<rect x="0" y="580" width="1024" height="444" fill="#fefefe"/>' in svg, name


def test_the_icons_are_drawn_from_the_svgs_by_the_script():
    with open(os.path.join(STATIC, "render-icons.sh")) as file:
        script = file.read()

    for name in SIZES:
        assert name in script, name
    assert os.access(os.path.join(STATIC, "render-icons.sh"), os.X_OK)
