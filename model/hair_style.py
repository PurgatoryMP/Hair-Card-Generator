from __future__ import annotations

from dataclasses import dataclass

@dataclass
class HairStyle:
    name: str = "Custom"
    length_pct: float = 94.0
    length_variation_pct: float = 12.0
    # Overall silhouette width at the root, middle, and tip of the card.
    # These percentages are measured against the usable card width after the safe margin.
    root_width_pct: float = 64.0
    middle_width_pct: float = 48.0
    tip_width_pct: float = 30.0

    primary_strands: int = 50
    secondary_strands: int = 50
    flyaway_strands: int = 20

    clump_count: int = 8
    clump_strength: float = 0.55

    wave_cycles: float = 2.0
    wave_amplitude_pct: float = 5.0
    secondary_wave_cycles: float = 4.0
    secondary_wave_amplitude_pct: float = 1.5

    frizz_pct: float = 0.7
    frizz_frequency: float = 1.0

    tip_spread_pct: float = 10.0
    tip_breakup: float = 0.20

    # Per-strand raster width at the root and tip.  strand_width_px is retained
    # as the end/tip width for backwards-compatible project files.
    strand_start_width_px: float = 1.55
    strand_width_px: float = 1.55
    strand_width_variation: float = 0.35

    opacity: int = 235
    secondary_opacity: int = 115
    flyaway_opacity: int = 145

    root_color: str = "#160E0A"
    mid_color: str = "#4A2816"
    tip_color: str = "#9A5C32"
    color_variation: float = 0.08

    highlight_probability: float = 0.06
    highlight_strength: float = 0.28
    highlight_color: str = "#E0B88A"

    # Distance from the card boundary in percent of the smaller dimension.
    safe_margin_pct: float = 3.0

    # Optional procedural braid structure. When disabled, the existing loose-hair
    # strand geometry is used unchanged. Braid controls shape the lateral motion
    # of strand groups around a shared centerline.
    braid_enabled: bool = False
    braid_strands: int = 3
    braid_cycles: float = 8.0
    braid_width_pct: float = 70.0
    braid_tightness: float = 0.75
    braid_taper_pct: float = 25.0
