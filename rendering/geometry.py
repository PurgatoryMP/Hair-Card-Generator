from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from model.hair_style import HairStyle


@dataclass(frozen=True)
class RenderProfile:
    t: np.ndarray
    envelope: np.ndarray
    smooth: np.ndarray
    smoother: np.ndarray
    width_pct: np.ndarray
    half_width: np.ndarray
    width_ratio: np.ndarray
    root_profile: np.ndarray
    tip_profile: np.ndarray
    alpha_fade: np.ndarray
    tip_break_profile: np.ndarray


def build_profile(style: HairStyle, usable_width: float, segments: int) -> RenderProfile:
    segments = max(2, int(segments))
    t = np.linspace(0.0, 1.0, segments, dtype=np.float32)
    smooth = t * t * (3.0 - 2.0 * t)
    smoother = smooth * smooth * (3.0 - 2.0 * smooth)
    envelope = np.power(np.clip(np.sin(np.pi * t), 0.0, None), 0.75).astype(np.float32)

    local_a = smooth.copy()
    local_b = np.clip((t - 0.5) * 2.0, 0.0, 1.0)
    local_b = local_b * local_b * (3.0 - 2.0 * local_b)
    width_pct = np.where(
        t <= 0.5,
        style.root_width_pct + (style.middle_width_pct - style.root_width_pct) * local_a,
        style.middle_width_pct + (style.tip_width_pct - style.middle_width_pct) * local_b,
    ).astype(np.float32)

    ratio = width_pct / 100.0
    half = (usable_width * ratio * 0.5).astype(np.float32)
    root = (1.0 - 0.18 * smoother).astype(np.float32)

    tip_u = np.clip((t - 0.58) / 0.42, 0.0, 1.0)
    tip_u = tip_u * tip_u * (3.0 - 2.0 * tip_u)
    tip = (1.0 - 0.93 * tip_u).astype(np.float32)

    alpha_u = np.clip((t - 0.76) / 0.24, 0.0, 1.0)
    alpha_u = alpha_u * alpha_u * (3.0 - 2.0 * alpha_u)
    alpha = (1.0 - 0.52 * alpha_u).astype(np.float32)

    break_u = np.clip((t - 0.62) / 0.38, 0.0, 1.0)
    break_u = break_u * break_u * (3.0 - 2.0 * break_u)

    return RenderProfile(
        t=t,
        envelope=envelope,
        smooth=smooth.astype(np.float32),
        smoother=smoother.astype(np.float32),
        width_pct=width_pct,
        half_width=half,
        width_ratio=ratio.astype(np.float32),
        root_profile=root,
        tip_profile=tip.astype(np.float32),
        alpha_fade=alpha.astype(np.float32),
        tip_break_profile=break_u.astype(np.float32),
    )


def build_mass_points(
    style: HairStyle,
    profile: RenderProfile,
    *,
    center_x: float,
    safe_margin: float,
    width: int,
    y_start: float,
    effective_length: float,
    clump_count: int,
    wave_amplitude: float,
):
    """Generate low-cost clump polylines."""
    t = profile.t
    y = y_start + effective_length * t
    envelope = np.clip(np.sin(np.pi * t), 0.0, None) ** 0.8
    clump_count = max(1, int(clump_count))
    for ci in range(clump_count):
        n = 0.5 if clump_count == 1 else ci / (clump_count - 1)
        phase = ci * 0.61
        wave = np.sin(math.tau * style.wave_cycles * t + phase) * wave_amplitude * envelope
        x = center_x + profile.half_width * (2.0 * n - 1.0) + wave
        x = np.clip(x, safe_margin, width - safe_margin)
        yield np.column_stack((x, y)).astype(np.float32)


def _noise_batch(t: np.ndarray, frequency: float, phases, offsets) -> np.ndarray:
    """Vectorized equivalent of SmoothNoise.sample for an array of t values."""
    freqs = np.asarray((1.0, 2.17, 4.43, 8.61, 15.7), dtype=np.float32)
    weights = np.asarray((1.0, 0.55, 0.28, 0.13, 0.06), dtype=np.float32)
    phase = np.asarray(phases, dtype=np.float32)[:, None]
    offset = np.asarray(offsets, dtype=np.float32)[:, None]
    values = np.sin(math.tau * (t[None, :] * frequency * freqs[:, None] + offset) + phase)
    return (values * weights[:, None]).sum(axis=0) / float(weights.sum())


def build_strand_batch(
    *,
    style: HairStyle,
    profile: RenderProfile,
    phases: np.ndarray,
    amp_scales: np.ndarray,
    root_norms: np.ndarray,
    clump_norms: np.ndarray,
    frizz_amplitude: float,
    wave_amplitude: float,
    secondary_amplitude: float,
    tip_spread: float,
    tip_offsets: np.ndarray,
    length_scales: np.ndarray,
    center_x: float,
    safe_margin: float,
    canvas_width: int,
    y_start: float,
    effective_length: float,
    noise_phases: np.ndarray,
    noise_offsets: np.ndarray,
):
    """Generate complete strand geometry for many strands using NumPy broadcasting."""
    t = profile.t[None, :]
    half = profile.half_width[None, :]
    ratio = profile.width_ratio[None, :]
    smooth = profile.smooth[None, :]
    envelope = profile.envelope[None, :]
    tip_break_profile = profile.tip_break_profile[None, :]

    base_x = (root_norms[:, None] - 0.5) * 2.0 * half
    clump_x = (clump_norms[:, None] - 0.5) * 2.0 * half
    base_x += (clump_x - base_x) * (smooth * style.clump_strength)

    wave = np.sin(math.tau * style.wave_cycles * t + phases[:, None])
    wave *= wave_amplitude * amp_scales[:, None] * envelope

    secondary_phase = phases * 1.71
    secondary = np.sin(math.tau * style.secondary_wave_cycles * t + secondary_phase[:, None])
    secondary *= secondary_amplitude * amp_scales[:, None] * envelope * ratio

    # Each strand gets its own deterministic five-frequency noise state. The
    # state is generated once, then all samples are evaluated in one vectorized pass.
    noise = np.zeros((len(phases), profile.t.size), dtype=np.float32)
    freqs = np.asarray((1.0, 2.17, 4.43, 8.61, 15.7), dtype=np.float32)
    weights = np.asarray((1.0, 0.55, 0.28, 0.13, 0.06), dtype=np.float32)
    for k in range(5):
        noise += 0.0 if k else 0.0
        # Broadcasting across strands and samples; the loop is only five terms.
        noise += weights[k] * np.sin(
            math.tau * (
                t * style.frizz_frequency * freqs[k]
                + noise_offsets[:, k, None]
            )
            + noise_phases[:, k, None]
        )
    noise /= float(weights.sum())
    micro = noise * frizz_amplitude * smooth * ratio

    tip_break = tip_offsets[:, None] * tip_spread * tip_break_profile * ratio
    x = center_x + base_x + wave + secondary + micro + tip_break
    x = np.clip(x, safe_margin, canvas_width - safe_margin).astype(np.float32)
    y = y_start + effective_length * length_scales[:, None] * t

    # Geometry is returned in pixels. y scaling by effective length is applied
    # by the renderer so a single batch can be generated at the card scale.
    return x, y


def build_strand_geometry(**kwargs):
    """Compatibility wrapper for callers that still render one strand."""
    phases = np.asarray([kwargs.pop("phase")], dtype=np.float32)
    noise_obj = kwargs.pop("noise")
    x, y = build_strand_batch(
        phases=phases,
        amp_scales=np.asarray([kwargs.pop("amp_scale")], dtype=np.float32),
        root_norms=np.asarray([kwargs.pop("root_norm")], dtype=np.float32),
        clump_norms=np.asarray([kwargs.pop("clump_target_norm")], dtype=np.float32),
        tip_offsets=np.asarray([kwargs.pop("tip_offset")], dtype=np.float32),
        length_scales=np.asarray([1.0], dtype=np.float32),
        effective_length=float(kwargs.pop("strand_length")),
        noise_phases=np.asarray([noise_obj.phases], dtype=np.float32),
        noise_offsets=np.asarray([noise_obj.offsets], dtype=np.float32),
        **kwargs,
    )
    return tuple(zip(x[0].tolist(), y[0].tolist()))
