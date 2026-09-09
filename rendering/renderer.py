from __future__ import annotations

import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from model.hair_style import HairStyle
from model.project import Project
from rendering.cache import RenderCache
from rendering.compositor import composite_tile
from rendering.geometry import RenderProfile, build_mass_points, build_profile, build_strand_batch
from rendering.noise import SmoothNoise
from utils.colors import hex_to_rgb
from utils.math import clamp

_DEFAULT_CACHE = RenderCache(max_entries=96, renderer_version=6)


def _rgb_array(hex_color: str) -> np.ndarray:
    return np.asarray(hex_to_rgb(hex_color), dtype=np.float32)


def _color_ramp(profile: RenderProfile, root, mid, tip) -> np.ndarray:
    t = profile.t[:, None]
    a = np.clip(t * 2.0, 0.0, 1.0)
    b = np.clip((t - 0.5) * 2.0, 0.0, 1.0)
    first = root[None, :] + (mid[None, :] - root[None, :]) * a
    second = mid[None, :] + (tip[None, :] - mid[None, :]) * b
    return np.where((t <= 0.5), first, second).astype(np.float32)


def _apply_braid_structure(
    x: np.ndarray,
    style: HairStyle,
    profile: RenderProfile,
    root_norms: np.ndarray,
    clump_norms: np.ndarray,
    phases: np.ndarray,
    amp_scales: np.ndarray,
) -> np.ndarray:
    """Transform loose strand positions into interweaving braid group paths.

    The existing strand deformation (wave, frizz, tip breakup, etc.) is retained.
    Only the lateral distribution is replaced by a small number of phase-offset
    group trajectories, producing the characteristic repeated crossings of a
    braid without requiring a separate raster backend.
    """
    if not getattr(style, "braid_enabled", False) or x.size == 0:
        return x

    count, points = x.shape
    group_count = max(2, min(5, int(getattr(style, "braid_strands", 3))))
    t = profile.t[None, :]
    half = profile.half_width[None, :]
    smooth = profile.smooth[None, :]

    # Remove the normal full-width root/clump placement. Braid strands instead
    # live around a handful of coherent trajectories. A small residual offset
    # preserves natural strand thickness within each woven section.
    clump_strength = float(style.clump_strength)
    base_x = (root_norms[:, None] - 0.5) * 2.0 * half
    clump_x = (clump_norms[:, None] - 0.5) * 2.0 * half
    loose_offset = base_x + (clump_x - base_x) * (smooth * clump_strength)

    # Three groups are the conventional braid. Additional groups are supported
    # for stylized braids, while the UI keeps the range deliberately small.
    group_ids = np.arange(count, dtype=np.int32) % group_count
    group_phase = (math.tau * group_ids / float(group_count)).astype(np.float32)[:, None]
    braid_cycles = max(1.0, float(getattr(style, "braid_cycles", 8.0)))
    width_factor = np.clip(float(getattr(style, "braid_width_pct", 70.0)) / 100.0, 0.0, 1.0)
    tightness = np.clip(float(getattr(style, "braid_tightness", 0.75)), 0.0, 1.0)
    taper = np.clip(float(getattr(style, "braid_taper_pct", 25.0)) / 100.0, 0.0, 0.9)

    # Higher tightness produces more compact, clearly separated braid lobes.
    amplitude = half * width_factor * (0.30 + 0.42 * tightness)
    taper_factor = 1.0 - taper * t
    weave = np.sin(math.tau * braid_cycles * t + group_phase)
    weave *= amplitude * taper_factor

    # Preserve a little per-strand variation inside each woven group.
    local_spread = (root_norms[:, None] - 0.5) * 0.12 * half
    local_spread *= (0.75 + 0.25 * amp_scales[:, None])

    # The braid path itself is centered, while the existing waves/frizz remain
    # in x. Removing loose_offset prevents the normal hair distribution from
    # fighting the braid trajectory.
    result = x - loose_offset + weave + local_spread
    return result.astype(np.float32)


class HairRenderer:
    """NumPy-accelerated procedural hair renderer with density-mask compositing."""

    def __init__(self, supersample: int = 2, cache: RenderCache | None = None):
        self.supersample = max(1, int(supersample))
        self.cache = cache or _DEFAULT_CACHE

    def _render_card_uncached(self, style: HairStyle, width: int, height: int, seed: int, show_background: bool) -> Image.Image:
        ss = self.supersample
        W = max(4, int(width * ss))
        H = max(4, int(height * ss))
        rng = np.random.default_rng(int(seed))
        py_rng = random.Random(int(seed))

        image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if show_background:
            bg = hex_to_rgb("#202020")
            ImageDraw.Draw(image).rectangle((0, 0, W, H), fill=(*bg, 255))

        min_dim = min(W, H)
        safe_margin = min_dim * (style.safe_margin_pct / 100.0)
        effective_length = max(8.0, (H - 2.0 * safe_margin) * (style.length_pct / 100.0))
        y_start = safe_margin
        usable_width = max(1.0, W - 2.0 * safe_margin)
        wave_amplitude = W * (style.wave_amplitude_pct / 100.0)
        secondary_amplitude = W * (style.secondary_wave_amplitude_pct / 100.0)
        frizz_amplitude = W * (style.frizz_pct / 100.0)
        tip_spread = W * (style.tip_spread_pct / 100.0)
        center_x = W * 0.5
        clump_count = max(0, int(style.clump_count))

        profile80 = build_profile(style, usable_width, 81)
        profile68 = build_profile(style, usable_width, 69)
        profile60 = build_profile(style, usable_width, 61)
        mass_profile = build_profile(style, usable_width, 70)

        root_rgb = _rgb_array(style.root_color)
        mid_rgb = _rgb_array(style.mid_color)
        tip_rgb = _rgb_array(style.tip_color)
        highlight_rgb = _rgb_array(style.highlight_color)
        colors80 = _color_ramp(profile80, root_rgb, mid_rgb, tip_rgb)
        colors68 = _color_ramp(profile68, root_rgb, mid_rgb, tip_rgb)
        colors60 = _color_ramp(profile60, root_rgb, mid_rgb, tip_rgb)

        # Low-frequency volumetric mass. It is deliberately kept separate from
        # the strand layer so density can be tuned without changing geometry.
        mass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        mass_draw = ImageDraw.Draw(mass)
        mass_width = max(1, int(min_dim * 0.010))
        if clump_count > 0 and not getattr(style, "braid_enabled", False):
            # Normal clump mass intentionally spans the loose-hair silhouette.
            # In braid mode it would create stray side rails that fight the
            # interweaving structure, so the braid relies on its strand-density
            # field instead.
            for pts in build_mass_points(style, mass_profile, center_x=center_x, safe_margin=safe_margin,
                                         width=W, y_start=y_start, effective_length=effective_length,
                                         clump_count=clump_count, wave_amplitude=wave_amplitude):
                mass_draw.line([(int(x), int(y)) for x, y in pts], fill=(*mid_rgb.astype(np.uint8), 22), width=mass_width, joint="curve")
        mass = mass.filter(ImageFilter.GaussianBlur(radius=max(1.0, 2.5 * ss)))
        image.alpha_composite(mass)

        # Two independent fields: visible appearance and accumulated density.
        # Density is later used as an alpha modulation pass, which gives dense
        # regions stronger lock structure without forcing every strand opaque.
        strand_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        strand_draw = ImageDraw.Draw(strand_layer)
        density_layer = Image.new("L", (W, H), 0)
        density_draw = ImageDraw.Draw(density_layer)

        def render_batch(count, profile, colors, opacity, width_multiplier, amp_lo, amp_hi, root_uniform, variation_scale,
                         tip_range, length_range, highlight_probability, highlight_allowed, noise_seed_base):
            count = max(0, int(count))
            if not count:
                return
            phases = rng.uniform(0.0, math.tau, count).astype(np.float32)
            amp_scales = rng.uniform(amp_lo, amp_hi, count).astype(np.float32)
            root_norms = (rng.triangular(0.0, 0.5, 1.0, count) if root_uniform == "triangular" else rng.uniform(0.0, 1.0, count)).astype(np.float32)
            if clump_count > 0:
                clump_ids = rng.integers(0, clump_count, count)
                clump_norms = (0.5 if clump_count == 1 else clump_ids / float(clump_count - 1)).astype(np.float32)
            else:
                # Zero clumps means a deliberately un-clumped distribution.
                # Keep the batch numerically valid and disable the clump blend.
                clump_norms = np.full(count, 0.5, dtype=np.float32)
            width_scales = rng.uniform(variation_scale[0], variation_scale[1], count).astype(np.float32)
            color_shifts = rng.uniform(-style.color_variation * variation_scale[2], style.color_variation * variation_scale[2], count).astype(np.float32)
            tip_offsets = rng.uniform(tip_range[0], tip_range[1], count).astype(np.float32)
            length_scales = rng.uniform(length_range[0], length_range[1], count).astype(np.float32)
            noise_phases = rng.uniform(0.0, math.tau, (count, 5)).astype(np.float32)
            noise_offsets = rng.uniform(0.0, 1000.0, (count, 5)).astype(np.float32)

            x, y = build_strand_batch(
                style=style, profile=profile, phases=phases, amp_scales=amp_scales,
                root_norms=root_norms, clump_norms=clump_norms,
                frizz_amplitude=frizz_amplitude, wave_amplitude=wave_amplitude,
                secondary_amplitude=secondary_amplitude, tip_spread=tip_spread,
                tip_offsets=tip_offsets, length_scales=length_scales,
                center_x=center_x, safe_margin=safe_margin, canvas_width=W,
                y_start=y_start, effective_length=effective_length,
                noise_phases=noise_phases, noise_offsets=noise_offsets,
            )
            if getattr(style, "braid_enabled", False):
                x = _apply_braid_structure(
                    x, style, profile, root_norms, clump_norms, phases, amp_scales
                )
                x = np.clip(x, safe_margin, W - safe_margin).astype(np.float32)
            if clump_count <= 0:
                # Remove only the clump attraction while preserving wave,
                # secondary wave, frizz, tip breakup, and length geometry.
                smooth = profile.smooth[None, :]
                half = profile.half_width[None, :]
                base_x = (root_norms[:, None] - 0.5) * 2.0 * half
                clump_x = (clump_norms[:, None] - 0.5) * 2.0 * half
                x -= (clump_x - base_x) * (smooth * style.clump_strength)
                x = np.clip(x, safe_margin, W - safe_margin).astype(np.float32)

            # Appearance is calculated for every strand/segment in one NumPy pass.
            # Strand width is independently controlled at the root and tip.
            # Smooth interpolation preserves the existing look when both values
            # are equal, while allowing deliberately thicker roots with fewer
            # strands for broader, more stylized hair.
            width_t = profile.t[None, :]
            width_interp = (
                style.strand_start_width_px
                + (style.strand_width_px - style.strand_start_width_px) * width_t
            )
            width_interp = np.maximum(0.0, width_interp)
            widths = np.maximum(
                0.45 * ss,
                width_interp * ss * width_multiplier
                * width_scales[:, None] * profile.root_profile[None, :] * profile.tip_profile[None, :],
            )
            shifts = (255.0 * color_shifts)[:, None, None]
            rgb = np.clip(colors[None, :, :] + shifts, 0.0, 255.0)
            if highlight_allowed:
                highlight = rng.random(count) < highlight_probability
                h = style.highlight_strength * profile.smoother[None, :]
                rgb = np.where(highlight[:, None, None], rgb * (1.0 - h[:, :, None]) + highlight_rgb[None, None, :] * h[:, :, None], rgb)

            alpha = np.broadcast_to(np.clip(opacity * profile.alpha_fade[None, :], 0, 255), (count, profile.t.size)).astype(np.uint8)
            density_alpha = np.clip(alpha.astype(np.float32) * (0.55 if width_multiplier < 1.0 else 0.78), 0, 255).astype(np.uint8)

            # Reduce the 81/69/61 samples to ten raster bands in one NumPy pass.
            # The Python loop below only handles Pillow draw calls.
            bands = 10
            point_count = x.shape[1]
            starts = np.asarray([(b * (point_count - 1)) // bands for b in range(bands)], dtype=np.int32)
            ends = np.asarray([((b + 1) * (point_count - 1)) // bands + 1 for b in range(bands)], dtype=np.int32)
            band_widths = np.empty((count, bands), dtype=np.int16)
            band_colors = np.empty((count, bands, 3), dtype=np.uint8)
            band_alpha = np.empty((count, bands), dtype=np.uint8)
            for b, (a0, a1) in enumerate(zip(starts, ends)):
                band_widths[:, b] = np.maximum(1, np.rint(widths[:, a0:a1].mean(axis=1))).astype(np.int16)
                band_colors[:, b] = np.clip(rgb[:, a0:a1].mean(axis=1), 0, 255).astype(np.uint8)
                band_alpha[:, b] = alpha[:, a0:a1].max(axis=1)

            for j in range(count):
                for b, (a0, a1) in enumerate(zip(starts, ends)):
                    pts = [(int(round(px)), int(round(py))) for px, py in zip(x[j, a0:a1], y[j, a0:a1])]
                    if len(pts) < 2:
                        continue
                    color = band_colors[j, b]
                    strand_draw.line(pts, fill=(int(color[0]), int(color[1]), int(color[2]), int(band_alpha[j, b])),
                                      width=int(band_widths[j, b]), joint="curve")
                full_pts = [(int(round(px)), int(round(py))) for px, py in zip(x[j], y[j])]
                density_draw.line(full_pts, fill=int(np.max(density_alpha[j])),
                                  width=max(1, int(round(float(np.mean(widths[j]))))), joint="curve")

        primary = max(0, int(style.primary_strands))
        render_batch(primary, profile80, colors80, style.opacity, 1.0, 0.78, 1.24, "triangular",
                     (1.0 - style.strand_width_variation, 1.0 + style.strand_width_variation, 1.0),
                     (-0.5, 0.5), (1.0 - style.length_variation_pct / 100.0, 1.0), style.highlight_probability, True, seed)
        secondary = max(0, int(style.secondary_strands))
        render_batch(secondary, profile68, colors68, style.secondary_opacity, 0.60, 0.72, 1.30, "uniform",
                     (0.55, 1.0, 0.7), (-0.7, 0.7), (1.0 - style.length_variation_pct / 100.0, 1.0), 0.0, False, seed + 1)
        flyaways = max(0, int(style.flyaway_strands))
        render_batch(flyaways, profile60, colors60, style.flyaway_opacity, 0.42, 0.90, 1.70, "uniform",
                     (0.2, 0.6, 1.0), (-1.0, 1.0), (1.0 - style.length_variation_pct / 100.0, 1.0), 0.0, False, seed + 2)

        # Density-mask pass. A small blur turns discrete strand coverage into a
        # continuous field. We only modulate alpha, preserving the RGB detail.
        density = np.asarray(density_layer, dtype=np.float32)
        density = np.minimum(255.0, density * 1.12)
        density = np.asarray(Image.fromarray(density.astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(0.35, 0.55 * ss))
        ), dtype=np.float32)

        rgba = np.asarray(strand_layer, dtype=np.uint8).copy()
        rgba[..., 3] = np.minimum(rgba[..., 3].astype(np.float32), density).astype(np.uint8)
        final_layer = Image.fromarray(rgba, mode="RGBA")
        image.alpha_composite(final_layer)

        if ss > 1:
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        return image

    def render_card(self, style: HairStyle, width: int, height: int, seed: int, show_background: bool = False) -> Image.Image:
        key = self.cache.key(style, width, height, seed, self.supersample, show_background)
        cached = self.cache.get(key)
        if cached is not None:
            return cached.copy()
        image = self._render_card_uncached(style, width, height, seed, show_background)
        self.cache.put(key, image)
        return image.copy()

    def render_sheet(self, project: Project) -> Image.Image:
        project.normalize_card_count()
        cell_w = project.width // project.columns
        cell_h = project.height // project.rows
        sheet = Image.new("RGBA", (project.width, project.height), (0, 0, 0, 0))
        for idx, card in enumerate(project.cards):
            row = idx // project.columns
            col = idx % project.columns
            x = col * cell_w
            y = row * cell_h
            w = cell_w if col < project.columns - 1 else project.width - x
            h = cell_h if row < project.rows - 1 else project.height - y
            composite_tile(sheet, self.render_card(card.style, w, h, card.seed), x, y)
        return sheet
