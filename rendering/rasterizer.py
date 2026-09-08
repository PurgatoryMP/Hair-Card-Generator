from __future__ import annotations

from PIL import ImageDraw

def draw_segment(draw: ImageDraw.ImageDraw, previous, current, color, alpha: int, width: int) -> None:
    """Draw one clipped raster segment."""
    draw.line([(int(previous[0]), int(previous[1])), (int(current[0]), int(current[1]))], fill=(*color, alpha), width=max(1,int(width)))
