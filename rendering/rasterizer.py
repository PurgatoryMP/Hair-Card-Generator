from __future__ import annotations

from PIL import ImageDraw


def draw_segment(draw: ImageDraw.ImageDraw, previous, current, color, alpha: int, width: int) -> None:
    """Draw one raster segment; retained for compatibility with callers."""
    draw.line(
        [(int(previous[0]), int(previous[1])), (int(current[0]), int(current[1]))],
        fill=(*color, alpha),
        width=max(1, int(width)),
    )


def _mean(values, start: int, end: int) -> float:
    """Return the arithmetic mean of a small rasterization band."""
    count = end - start
    return sum(values[start:end]) / count if count else 0.0


def draw_strand_banded(
    draw: ImageDraw.ImageDraw,
    points: tuple[tuple[float, float], ...],
    widths: tuple[float, ...],
    colors: tuple[tuple[int, int, int], ...],
    alphas: tuple[int, ...],
    *,
    bands: int = 10,
) -> None:
    """Rasterize a strand using a small number of tapered polyline bands.

    The previous renderer emitted one Pillow line primitive per segment. This
    method keeps the same generated geometry but collapses those primitives
    into a handful of longer polylines. Width, color, and alpha are averaged
    inside each band, retaining the visual taper while dramatically reducing
    Python/Pillow call overhead.
    """
    count = len(points)
    if count < 2:
        return

    bands = max(1, min(int(bands), count - 1))
    for band in range(bands):
        start = (band * (count - 1)) // bands
        end = ((band + 1) * (count - 1)) // bands + 1
        if end <= start + 1:
            continue

        width = max(1, round(_mean(widths, start, end)))
        alpha = max(0, min(255, round(_mean(alphas, start, end))))
        r = max(0, min(255, round(_mean([c[0] for c in colors], start, end))))
        g = max(0, min(255, round(_mean([c[1] for c in colors], start, end))))
        b = max(0, min(255, round(_mean([c[2] for c in colors], start, end))))

        draw.line(
            [(round(x), round(y)) for x, y in points[start:end]],
            fill=(r, g, b, alpha),
            width=width,
            joint="curve",
        )
