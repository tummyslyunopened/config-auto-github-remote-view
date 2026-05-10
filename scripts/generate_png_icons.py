"""
Generate the PNG launch icons for the config-auto-github status dashboard.

The SVG (status/static/status/icon.svg) is the source of truth for the visual
design; this script redraws the same shapes with Pillow so we can produce
properly sized PNGs without pulling in a system SVG rasterizer (cairo / rsvg).

Run with:
    uvx --from pillow python scripts/generate_png_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Colors mirror the dashboard theme (see status/templates/status/dashboard.html).
BG = (14, 17, 22, 255)         # #0e1116 outer panel
PANEL = (22, 27, 34, 255)      # #161b22 inner panel
PANEL_BORDER = (48, 54, 61, 255)  # #30363d
HEAD = (33, 38, 45, 255)       # #21262d bot face fill
ACCENT = (88, 166, 255, 255)   # #58a6ff blue (github accent)
OK = (63, 185, 80, 255)        # #3fb950 status green
OK_HALO = (63, 185, 80, 72)    # translucent green halo


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=0):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw_icon(size: int, *, maskable: bool = False) -> Image.Image:
    """Draw the icon at the given square size.

    The base SVG uses a 512-unit viewBox. We scale all coordinates uniformly
    by ``size / 512``. ``maskable`` shrinks the artwork into the inner 80% safe
    zone that Android uses for adaptive launcher masks.
    """
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scale factor: viewBox is 512.
    if maskable:
        # Maskable icons need to keep critical content inside the central 80%.
        # We paint the background full-bleed and draw the artwork shrunk.
        s = (size * 0.8) / 512
        offset = size * 0.1
        # Full-bleed background so the mask never reveals transparent corners.
        draw.rectangle((0, 0, size, size), fill=BG)
    else:
        s = size / 512
        offset = 0.0

    def x(v):
        return offset + v * s

    def y(v):
        return offset + v * s

    def r(v):
        return v * s

    # Outer panel (only drawn here when not maskable — maskable already filled).
    if not maskable:
        _rounded_rect(draw, (x(0), y(0), x(512), y(512)), radius=r(96), fill=BG)

    # Inner panel.
    _rounded_rect(
        draw,
        (x(56), y(56), x(456), y(456)),
        radius=r(64),
        fill=PANEL,
        outline=PANEL_BORDER,
        width=max(1, int(round(8 * s))),
    )

    # Antenna stem.
    stem_w = max(1, int(round(10 * s)))
    draw.line(
        ((x(256), y(188)), (x(256), y(138))),
        fill=ACCENT,
        width=stem_w,
    )

    # Status halo + dot at top of antenna.
    halo_r = r(34)
    cx, cy = x(256), y(120)
    draw.ellipse(
        (cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r),
        outline=OK,
        width=max(1, int(round(6 * s))),
    )
    dot_r = r(22)
    draw.ellipse(
        (cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r),
        fill=OK,
    )

    # Bot face panel.
    _rounded_rect(
        draw,
        (x(132), y(188), x(380), y(396)),
        radius=r(44),
        fill=HEAD,
        outline=ACCENT,
        width=max(1, int(round(8 * s))),
    )

    # Eyes.
    eye_r = r(22)
    for ex_, ey_ in ((202, 272), (310, 272)):
        ecx, ecy = x(ex_), y(ey_)
        draw.ellipse(
            (ecx - eye_r, ecy - eye_r, ecx + eye_r, ecy + eye_r),
            fill=OK,
        )

    # Mouth slot.
    _rounded_rect(
        draw,
        (x(188), y(334), x(324), y(350)),
        radius=r(8),
        fill=ACCENT,
    )

    return img


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    out_dir = here / 'status' / 'static' / 'status'
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        ('icon-192.png', 192, False),
        ('icon-512.png', 512, False),
        ('icon-512-maskable.png', 512, True),
        ('apple-touch-icon.png', 180, False),
    ]
    for name, size, maskable in targets:
        img = _draw_icon(size, maskable=maskable)
        out = out_dir / name
        img.save(out, format='PNG', optimize=True)
        print(f'wrote {out} ({size}x{size}{", maskable" if maskable else ""})')


if __name__ == '__main__':
    main()
