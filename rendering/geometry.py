from __future__ import annotations

import math
from dataclasses import dataclass

from model.hair_style import HairStyle
from utils.math import lerp, smoothstep, smootherstep

@dataclass(frozen=True)
class RenderProfile:
    """Precomputed per-segment values shared by every strand on a card."""
    t: tuple[float, ...]
    envelope: tuple[float, ...]
    smooth: tuple[float, ...]
    smoother: tuple[float, ...]
    width_pct: tuple[float, ...]
    half_width: tuple[float, ...]
    width_ratio: tuple[float, ...]
    root_profile: tuple[float, ...]
    tip_profile: tuple[float, ...]
    alpha_fade: tuple[float, ...]
    tip_break_profile: tuple[float, ...]

def build_profile(style: HairStyle, usable_width: float, segments: int) -> RenderProfile:
    """Build a reusable lookup table for the hot strand loop."""
    segments = max(2, int(segments))
    t = tuple(i / (segments - 1) for i in range(segments))
    smooth = tuple(smoothstep(v) for v in t)
    smoother = tuple(smootherstep(v) for v in t)
    envelope = tuple(math.sin(math.pi * v) ** 0.75 for v in t)
    width_pct=[]
    half=[]
    ratio=[]
    root=[]
    tip=[]
    alpha=[]
    tip_break=[]
    for i,v in enumerate(t):
        if v <= 0.5:
            local=smoothstep(v*2.0)
            wp=lerp(style.root_width_pct,style.middle_width_pct,local)
        else:
            local=smoothstep((v-0.5)*2.0)
            wp=lerp(style.middle_width_pct,style.tip_width_pct,local)
        width_pct.append(wp)
        ratio.append(wp/100.0)
        half.append(usable_width*(wp/100.0)*0.5)
        root.append(1.0-0.18*smoother[i])
        tip.append(1.0-0.93*smootherstep(max(0.0,(v-0.58)/0.42)))
        alpha.append(1.0-0.52*smootherstep(max(0.0,(v-0.76)/0.24)))
        tip_break.append(smootherstep(max(0.0,(v-0.62)/0.38)))
    return RenderProfile(t,envelope,smooth,smoother,tuple(width_pct),tuple(half),tuple(ratio),tuple(root),tuple(tip),tuple(alpha),tuple(tip_break))

def build_mass_points(style: HairStyle, profile: RenderProfile, *, center_x: float, safe_margin: float, width: int, y_start: float, effective_length: float, clump_count: int, wave_amplitude: float):
    """Generate the low-cost volumetric clump lines used beneath strands."""
    for ci in range(max(1, clump_count)):
        n=0.5 if clump_count==1 else ci/(clump_count-1)
        pts=[]
        phase=ci*0.61
        for i,t in enumerate(profile.t):
            wave=math.sin(math.tau*style.wave_cycles*t+phase)*wave_amplitude*math.sin(math.pi*t)**0.8
            x=center_x+lerp(-profile.half_width[i],profile.half_width[i],n)
            pts.append((max(safe_margin,min(width-safe_margin,x+wave)),y_start+effective_length*t))
        yield pts
