#!/usr/bin/env python3
"""Fork: rebuilds the bundled symbolic icons whose upstream drawings were malformed.

Upstream's drawings had these defects:
- The gear's toothed outline sat low on its hole and ran past the bottom of the 16 px canvas,
  so it rendered with a flat bottom and an off-centre dot.
- The hearts were asymmetric (cusp at x=7.5, tip at x=8, a spur at the tip) and sat 0.5 px
  left of centre.
- The play triangle was 10 px tall beside 14 px pause bars and sat 0.6 px high, so the button
  shrank and grew as it toggled.

Here they are built from geometry: centred on (8, 8), symmetric, reproducible.

    python3 tools/ebb_symbolic_icons.py    # rewrites the files under icons/hicolor/scalable
"""
import math
from pathlib import Path

ICONS = Path(__file__).resolve().parent.parent / "icons" / "hicolor" / "scalable"
CENTER = (8.0, 8.0)


def num(value):
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def pt(p):
    return f"{num(p[0])} {num(p[1])}"


def polar(radius, degrees):
    a = math.radians(degrees)
    return (CENTER[0] + radius * math.cos(a), CENTER[1] + radius * math.sin(a))


def toward(a, b, distance):
    """The point `distance` from a toward b, at most halfway."""
    length = math.dist(a, b)
    t = min(distance / length, 0.5) if length else 0.0
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def rounded_polygon(points, radius):
    """A closed path through `points`, each corner rounded by a quadratic of size `radius`."""
    parts = []
    for i, p in enumerate(points):
        before, after = points[i - 1], points[(i + 1) % len(points)]
        parts.append(f"{'M' if i == 0 else 'L'}{pt(toward(p, before, radius))}"
                     f"Q{pt(p)} {pt(toward(p, after, radius))}")
    return "".join(parts) + "Z"


def circle(radius):
    top, bottom = (CENTER[0], CENTER[1] - radius), (CENTER[0], CENTER[1] + radius)
    r = num(radius)
    return f"M{pt(top)}A{r} {r} 0 1 0 {pt(bottom)}A{r} {r} 0 1 0 {pt(top)}Z"


def gear(teeth=8, tip=7.5, root=5.5, tip_half=8.5, root_half=14.0, hole=2.4, corner=0.5):
    """Trapezoid teeth on a root circle, one tooth pointing up, with a round hole."""
    pitch = 360.0 / teeth
    points = []
    for i in range(teeth):
        a = -90.0 + i * pitch
        points += [polar(root, a - root_half), polar(tip, a - tip_half),
                   polar(tip, a + tip_half), polar(root, a + root_half)]
        gap = pitch - 2 * root_half  # the root arc between this tooth and the next
        points += [polar(root, a + root_half + gap * k / 3) for k in (1, 2)]
    return rounded_polygon(points, corner) + circle(hole)


# The left half of the heart, from the tip up to the cusp: cubic segments (c1, c2, end).
_HEART_TIP = (8.0, 14.15)
_HEART_LEFT = [
    ((7.85, 14.15), (7.70, 14.10), (7.55, 14.00)),
    ((3.70, 10.80), (1.50, 8.80), (1.50, 5.90)),
    ((1.50, 4.00), (3.00, 2.50), (4.90, 2.50)),
    ((6.10, 2.50), (7.30, 3.10), (8.00, 4.10)),
]


def heart(scale=1.0, dy=-0.25):
    """Symmetric about x=8: the left half mirrored. `scale` shrinks it about its centre."""
    cy = (2.5 + 14.15) / 2 + dy  # the bounding-box centre

    def place(p):
        return (8.0 + (p[0] - 8.0) * scale, cy + (p[1] + dy - cy) * scale)

    def mirror(p):
        return (16.0 - p[0], p[1])

    path = [f"M{pt(place(_HEART_TIP))}"]
    for c1, c2, end in _HEART_LEFT:
        path.append(f"C{pt(place(c1))} {pt(place(c2))} {pt(place(end))}")
    starts = [_HEART_TIP] + [segment[2] for segment in _HEART_LEFT]
    for k in range(len(_HEART_LEFT) - 1, -1, -1):  # back down the right side
        c1, c2, _end = _HEART_LEFT[k]
        path.append(f"C{pt(place(mirror(c2)))} {pt(place(mirror(c1)))} {pt(place(mirror(starts[k])))}")
    return "".join(path) + "Z"


def play():
    """A rounded triangle as tall as the pause bars' visual weight; optically centred (+0.85)."""
    return rounded_polygon([(3.5, 1.0), (14.75, 8.0), (3.5, 15.0)], 1.15)


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">\n'
            f"  {body}\n</svg>\n")


def filled(d, evenodd=False):
    rule = ' fill-rule="evenodd"' if evenodd else ""
    return f'<path fill="currentColor"{rule} d="{d}"/>'


def outlined(d, width=1.4):
    return (f'<path fill="none" stroke="currentColor" stroke-width="{num(width)}" '
            f'stroke-linejoin="round" d="{d}"/>')


def build():
    # The outline heart's stroke straddles its path, so its path is drawn smaller: the outer
    # edge then matches the filled heart and toggling a favorite doesn't change its size.
    outline = outlined(heart(scale=0.9))
    return {
        "actions/hiresti-gear-symbolic.svg": svg(filled(gear(), evenodd=True)),
        "status/hiresti-favorite-symbolic.svg": svg(filled(heart())),
        "status/emblem-favorite-symbolic.svg": svg(filled(heart())),
        "status/hiresti-favorite-outline-symbolic.svg": svg(outline),
        "status/non-starred-symbolic.svg": svg(outline),
        "actions/media-playback-start-symbolic.svg": svg(filled(play())),
    }


if __name__ == "__main__":
    for relative, text in build().items():
        path = ICONS / relative
        assert path.exists(), f"unexpected icon path {path}"
        path.write_text(text)
        print(f"wrote {relative}")
