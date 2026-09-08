from __future__ import annotations

from .math import clamp, lerp

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Convert a hexadecimal color string to an RGB tuple.

        Args:
            value: Parameter used by this operation.

        Returns:
            tuple[int, int, int]: The operation result.
    """
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

def rgb_to_hex(color: tuple[int, int, int]) -> str:
    """Convert an RGB tuple to a hexadecimal color string.

        Args:
            color: Parameter used by this operation.

        Returns:
            str: The operation result.
    """
    return "#%02X%02X%02X" % color

def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float):
    """Linearly interpolate between two RGB colors.

        Args:
            a: Parameter used by this operation.
            b: Parameter used by this operation.
            t: Parameter used by this operation.
    """
    return tuple(int(lerp(x, y, t)) for x, y in zip(a, b))

