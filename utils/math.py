from __future__ import annotations

import math

def clamp(v: float, lo: float, hi: float) -> float:
    """Clamp a numeric value to an inclusive range.

        Args:
            v: Parameter used by this operation.
            lo: Parameter used by this operation.
            hi: Parameter used by this operation.

        Returns:
            float: The operation result.
    """
    return max(lo, min(hi, v))

def lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between two numeric values.

        Args:
            a: Parameter used by this operation.
            b: Parameter used by this operation.
            t: Parameter used by this operation.

        Returns:
            float: The operation result.
    """
    return a + (b - a) * t

def smoothstep(t: float) -> float:
    """Apply a cubic smoothstep interpolation to a normalized value.

        Args:
            t: Parameter used by this operation.

        Returns:
            float: The operation result.
    """
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def smootherstep(t: float) -> float:
    """Apply a quintic smootherstep interpolation to a normalized value.

        Args:
            t: Parameter used by this operation.

        Returns:
            float: The operation result.
    """
    t = clamp(t, 0.0, 1.0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

