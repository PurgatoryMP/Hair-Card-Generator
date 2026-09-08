from __future__ import annotations

import math
import random
from PIL import Image, ImageDraw, ImageFilter

from model.hair_style import HairStyle
from model.project import Project
from rendering.cache import RenderCache
from rendering.compositor import composite_tile
from rendering.geometry import RenderProfile, build_mass_points, build_profile
from rendering.noise import SmoothNoise
from rendering.rasterizer import draw_segment
from utils.colors import hex_to_rgb, lerp_color
from utils.math import clamp, lerp

_DEFAULT_CACHE = RenderCache(max_entries=96, renderer_version=2)

class HairRenderer:
    """Procedural hair-card renderer with precomputed profiles and card caching."""
    def __init__(self, supersample: int = 2, cache: RenderCache | None = None):
        self.supersample=max(1,int(supersample))
        self.cache=cache or _DEFAULT_CACHE

    @staticmethod
    def _random_style_color(rng: random.Random, base: tuple[int,int,int], variation: float):
        delta=255.0*variation
        return tuple(int(clamp(channel+rng.uniform(-delta,delta),0,255)) for channel in base)

    def _render_card_uncached(self, style: HairStyle, width: int, height: int, seed: int, show_background: bool) -> Image.Image:
        ss=self.supersample
        W=max(4,int(width*ss)); H=max(4,int(height*ss))
        rng=random.Random(seed)
        image=Image.new("RGBA",(W,H),(0,0,0,0)); draw=ImageDraw.Draw(image)
        if show_background:
            bg=hex_to_rgb("#202020"); draw.rectangle((0,0,W,H),fill=(*bg,255))
        min_dim=min(W,H)
        safe_margin=min_dim*(style.safe_margin_pct/100.0)
        effective_length=max(8.0,(H-2.0*safe_margin)*(style.length_pct/100.0))
        y_start=safe_margin
        usable_width=max(1.0,W-2.0*safe_margin)
        wave_amplitude=W*(style.wave_amplitude_pct/100.0)
        secondary_amplitude=W*(style.secondary_wave_amplitude_pct/100.0)
        frizz_amplitude=W*(style.frizz_pct/100.0)
        tip_spread=W*(style.tip_spread_pct/100.0)
        center_x=W*0.5
        clump_count=max(1,int(style.clump_count))
        max_segments=max(80,68,60)
        profile80=build_profile(style,usable_width,81)
        profile68=build_profile(style,usable_width,69)
        profile60=build_profile(style,usable_width,61)
        mass_profile=build_profile(style,usable_width,70)
        mid_rgb=hex_to_rgb(style.mid_color)
        root_rgb=hex_to_rgb(style.root_color)
        tip_rgb=hex_to_rgb(style.tip_color)
        highlight_rgb=hex_to_rgb(style.highlight_color)
        # Precompute the base color ramp once.
        def color_ramp(profile: RenderProfile):
            out=[]
            for t in profile.t:
                if t<0.5: c=lerp_color(root_rgb,mid_rgb,t*2.0)
                else: c=lerp_color(mid_rgb,tip_rgb,(t-0.5)*2.0)
                out.append(c)
            return tuple(out)
        colors80=color_ramp(profile80); colors68=color_ramp(profile68); colors60=color_ramp(profile60)

        mass=Image.new("RGBA",(W,H),(0,0,0,0)); mass_draw=ImageDraw.Draw(mass)
        for pts in build_mass_points(style,mass_profile,center_x=center_x,safe_margin=safe_margin,width=W,y_start=y_start,effective_length=effective_length,clump_count=clump_count,wave_amplitude=wave_amplitude):
            mass_draw.line([(int(x),int(y)) for x,y in pts],fill=(*mid_rgb,22),width=max(1,int(min_dim*0.010)))
        mass=mass.filter(ImageFilter.GaussianBlur(radius=max(1.0,2.5*ss)))
        image.alpha_composite(mass)

        def draw_strand(root_norm,clump_target_norm,phase,amp_scale,noise_seed,width_scale,color_shift,tip_offset,length_scale,opacity,width_multiplier,is_highlight,profile,colors):
            noise=SmoothNoise(noise_seed)
            prev=None
            shift=255.0*color_shift
            strand_length=effective_length*clamp(length_scale,0.05,1.0)
            for i,t in enumerate(profile.t):
                envelope=profile.envelope[i]; half=profile.half_width[i]; ratio=profile.width_ratio[i]
                strand_x=(root_norm-0.5)*2.0*half
                clump_x=(clump_target_norm-0.5)*2.0*half
                base_x=strand_x+(clump_x-strand_x)*(profile.smooth[i]*style.clump_strength)
                macro=math.sin(math.tau*style.wave_cycles*t+phase)*wave_amplitude*amp_scale*envelope
                secondary=math.sin(math.tau*style.secondary_wave_cycles*t+phase*1.71)*secondary_amplitude*amp_scale*envelope*ratio
                micro=noise.sample(t,style.frizz_frequency)*frizz_amplitude*profile.smooth[i]*ratio
                tip_break=tip_offset*tip_spread*profile.tip_break_profile[i]*ratio
                x=clamp(center_x+base_x+macro+secondary+micro+tip_break,safe_margin,W-safe_margin)
                y=y_start+strand_length*t
                width_px=max(0.45*ss,style.strand_width_px*ss*width_multiplier*width_scale*profile.root_profile[i]*profile.tip_profile[i])
                base_color=colors[i]
                color=tuple(int(clamp(c+shift,0,255)) for c in base_color)
                if is_highlight:
                    h=style.highlight_strength*profile.smoother[i]
                    color=lerp_color(color,highlight_rgb,h)
                alpha=int(clamp(opacity*profile.alpha_fade[i],0,255))
                cur=(x,y)
                if prev is not None: draw_segment(draw,prev,cur,color,alpha,round(width_px))
                prev=cur

        primary=max(0,int(style.primary_strands))
        for _ in range(primary):
            root_norm=rng.triangular(0.0,1.0,0.5); ci=rng.randrange(clump_count); clump_norm=0.5 if clump_count==1 else ci/(clump_count-1)
            draw_strand(root_norm,clump_norm,rng.uniform(0,math.tau),rng.uniform(0.78,1.24),rng.randrange(0,2**31-1),rng.uniform(1.0-style.strand_width_variation,1.0+style.strand_width_variation),rng.uniform(-style.color_variation,style.color_variation),rng.uniform(-0.5,0.5),rng.uniform(1.0-style.length_variation_pct/100.0,1.0),style.opacity,1.0,rng.random()<style.highlight_probability,profile80,colors80)
        secondary=max(0,int(style.secondary_strands))
        for _ in range(secondary):
            root_norm=rng.uniform(0.0,1.0); ci=rng.randrange(clump_count); clump_norm=0.5 if clump_count==1 else ci/(clump_count-1)
            draw_strand(root_norm,clump_norm,rng.uniform(0,math.tau),rng.uniform(0.72,1.30),rng.randrange(0,2**31-1),rng.uniform(0.55,1.0),rng.uniform(-style.color_variation*0.7,style.color_variation*0.7),rng.uniform(-0.7,0.7),rng.uniform(1.0-style.length_variation_pct/100.0,1.0),style.secondary_opacity,0.60,False,profile68,colors68)
        for _ in range(max(0,int(style.flyaway_strands))):
            root_norm=rng.uniform(0.0,1.0); ci=rng.randrange(clump_count); clump_norm=0.5 if clump_count==1 else ci/(clump_count-1)
            draw_strand(root_norm,clump_norm,rng.uniform(0,math.tau),rng.uniform(0.9,1.7),rng.randrange(0,2**31-1),rng.uniform(0.2,0.6),rng.uniform(-style.color_variation,style.color_variation),rng.uniform(-1.0,1.0),rng.uniform(1.0-style.length_variation_pct/100.0,1.0),style.flyaway_opacity,0.42,False,profile60,colors60)
        if ss>1: image=image.resize((width,height),Image.Resampling.LANCZOS)
        return image

    def render_card(self, style: HairStyle, width: int, height: int, seed: int, show_background: bool=False) -> Image.Image:
        key=self.cache.key(style,width,height,seed,self.supersample,show_background)
        cached=self.cache.get(key)
        if cached is not None: return cached
        image=self._render_card_uncached(style,width,height,seed,show_background)
        self.cache.put(key,image)
        return image.copy()

    def render_sheet(self, project: Project) -> Image.Image:
        project.normalize_card_count()
        cell_w=project.width//project.columns; cell_h=project.height//project.rows
        sheet=Image.new("RGBA",(project.width,project.height),(0,0,0,0))
        for idx,card in enumerate(project.cards):
            row=idx//project.columns; col=idx%project.columns; x=col*cell_w; y=row*cell_h
            w=cell_w if col<project.columns-1 else project.width-x; h=cell_h if row<project.rows-1 else project.height-y
            composite_tile(sheet,self.render_card(card.style,w,h,card.seed),x,y)
        return sheet
