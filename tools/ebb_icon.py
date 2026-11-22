#!/usr/bin/env python3
"""Fork: generates Ebb's app icon (SVG + hicolor PNGs).

Three wave strokes form an E; the middle one is shorter, the tide pulling back.
    python3 tools/ebb_icon.py          # needs rsvg-convert for the PNGs
"""
import os
import subprocess
import sys

APP_ID = "io.github.henryprzygocki.Ebb"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons", "hicolor")
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def wave(x0, y, length, wavelength=32.0, amp=3.4):
    """A sine-like stroke from x0 along y: quadratic half-waves, mirrored with T."""
    half = wavelength / 2
    d = [f"M{x0:g} {y:g}", f"Q{x0 + half / 2:g} {y - 2 * amp:g} {x0 + half:g} {y:g}"]
    x = x0 + half
    while x + half <= x0 + length + 1e-6:
        x += half
        d.append(f"T{x:g} {y:g}")
    return " ".join(d)


def svg():
    strokes = "\n    ".join(
        f'<path d="{wave(32, y, length)}"/>' for y, length in ((43, 64), (64, 32), (85, 64))
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="sea" x1="0" y1="0" x2="0.35" y2="1">
      <stop offset="0" stop-color="#1a8fb5"/>
      <stop offset="1" stop-color="#0b2b5e"/>
    </linearGradient>
    <linearGradient id="foam" x1="0" y1="36" x2="0" y2="92" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#f4fbff"/>
      <stop offset="1" stop-color="#9fe6f0"/>
    </linearGradient>
    <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0.82" stop-color="#000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity="0.22"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="112" height="112" rx="28" fill="url(#sea)"/>
  <rect x="8" y="8" width="112" height="112" rx="28" fill="url(#shade)"/>
  <g fill="none" stroke="url(#foam)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">
    {strokes}
  </g>
</svg>
'''


def main():
    scalable = os.path.join(ROOT, "scalable", "apps", f"{APP_ID}.svg")
    with open(scalable, "w", encoding="utf-8") as fh:
        fh.write(svg())
    for size in SIZES:
        out = os.path.join(ROOT, f"{size}x{size}", "apps", f"{APP_ID}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), scalable, "-o", out], check=True)
    print(f"wrote {scalable} and {len(SIZES)} PNGs")


if __name__ == "__main__":
    sys.exit(main())
