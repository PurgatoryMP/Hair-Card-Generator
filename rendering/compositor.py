from __future__ import annotations

from PIL import Image

def composite_tile(sheet: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    """Composite a rendered card tile into a trim sheet."""
    sheet.alpha_composite(tile,(x,y))
