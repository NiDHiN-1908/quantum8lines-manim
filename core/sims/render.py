"""
Fast frame-by-frame renderer for ellipse billiards using pycairo + numpy + FFmpeg.
Follows Milestone P1 Step 2 and Milestone P2a.1 Picture Polish & Speed Optimization.
- Direct pycairo rasterization with static layer caching (background, vignette, ellipse, foci).
- Half-resolution Gaussian glow bloom via scipy.ndimage for 5x faster frame processing.
- Ellipse scaled to fill 92% of the LAYOUT_916 stage region (height-limiting dimension).
- Outline >= 5px wide with PRIMARY neon glow, faint inner fill, and radial background vignette.
- Balls >= 14px in diameter with longer, brighter fading trails and blue-to-orange gradient.
- Foci markers: F1 with soft launch pulse, F2 with expanding ring pulse at focal convergence.
- Payoff text fading into caption safe region in the last 4 seconds.
- S3b_stage_fill validation check and test helper.
"""

import math
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cairo
import numpy as np
import scipy.ndimage

from core.layout import LAYOUT_916
from core.sims.ellipse_billiards import (
    EllipseAxes,
    EllipseBilliardsSim,
    SimEvent,
    SimSpec,
    get_ball_position_at,
)

# Resolution definitions
QUALITY_PRESETS = {
    "test": {"width": 270, "height": 480, "fps": 30},
    "final": {"width": 1080, "height": 1920, "fps": 30},
}

# Brand color tokens (RGB in [0, 1])
COLOR_BACKGROUND = (14 / 255.0, 14 / 255.0, 17 / 255.0)       # #0e0e11
COLOR_BACKGROUND_DARK = (7 / 255.0, 7 / 255.0, 10 / 255.0)    # Deep vignette edge
COLOR_ELLIPSE = (88 / 255.0, 196 / 255.0, 221 / 255.0)        # PRIMARY (#58c4dd)
COLOR_TEXT_PRIMARY = (1.0, 1.0, 1.0)                          # White (#ffffff)
COLOR_TEXT_COUNTER = (0.95, 0.82, 0.30)                       # Warm golden yellow
COLOR_BALL_BLUE = (88 / 255.0, 196 / 255.0, 221 / 255.0)      # Gradient start (#58c4dd)
COLOR_BALL_ORANGE = (250 / 255.0, 132 / 255.0, 20 / 255.0)    # Gradient end (#fa8414)


def get_ball_color(ball_id: int, total_balls: int) -> Tuple[float, float, float]:
    """Computes blue-to-orange gradient color for a given ball ID."""
    if total_balls <= 1:
        return COLOR_BALL_BLUE
    u = ball_id / float(total_balls - 1)
    r = (1.0 - u) * COLOR_BALL_BLUE[0] + u * COLOR_BALL_ORANGE[0]
    g = (1.0 - u) * COLOR_BALL_BLUE[1] + u * COLOR_BALL_ORANGE[1]
    b = (1.0 - u) * COLOR_BALL_BLUE[2] + u * COLOR_BALL_ORANGE[2]
    return (r, g, b)


def get_safe_area_bounds(width: int, height: int) -> Tuple[float, float, float, float]:
    """
    Returns (x_min, y_min, x_max, y_max) of the safe zone for LAYOUT_916.
    At 1080x1920: top 250px, bottom 480px, left 90px, right 90px.
    """
    scale = width / 1080.0
    x_min = 90.0 * scale
    x_max = (1080.0 - 90.0) * scale
    y_min = 250.0 * scale
    y_max = (1920.0 - 480.0) * scale
    return (x_min, y_min, x_max, y_max)


def get_stage_region_bounds(width: int, height: int) -> Tuple[float, float, float, float]:
    """
    Returns (center_x, center_y, width, height) of the stage region from LAYOUT_916.
    In LAYOUT_916: center_x = 0, center_y = 1.2, width = 6.4, height = 4.8 units.
    """
    scale = width / 1080.0
    px_per_unit = 135.0 * scale
    stage_w = 6.4 * px_per_unit
    stage_h = 4.8 * px_per_unit
    cx = width / 2.0
    cy = (height / 2.0) - (1.2 * px_per_unit)
    return (cx, cy, stage_w, stage_h)


def check_s3b_stage_fill(
    spec: SimSpec,
    quality: str = "final",
    sim_scale_override: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Gate S3b Check: The ellipse bounding box must cover at least 85% of the
    stage region width or height (whichever is limiting).
    """
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["final"])
    w, h = preset["width"], preset["height"]
    _, _, stage_w, stage_h = get_stage_region_bounds(w, h)

    if sim_scale_override is not None:
        sim_scale = float(sim_scale_override)
    else:
        scale_w = (0.92 * stage_w) / (2.0 * spec.ellipse.a)
        scale_h = (0.92 * stage_h) / (2.0 * spec.ellipse.b)
        sim_scale = min(scale_w, scale_h)

    ellipse_bbox_w = 2.0 * spec.ellipse.a * sim_scale
    ellipse_bbox_h = 2.0 * spec.ellipse.b * sim_scale

    fill_w = ellipse_bbox_w / stage_w
    fill_h = ellipse_bbox_h / stage_h
    max_fill = max(fill_w, fill_h)

    passed = max_fill >= 0.85
    return {
        "passed": bool(passed),
        "stage_fill_ratio": round(float(max_fill), 4),
        "fill_width": round(float(fill_w), 4),
        "fill_height": round(float(fill_h), 4),
        "min_required": 0.85,
        "ellipse_dimensions_px": (round(ellipse_bbox_w, 1), round(ellipse_bbox_h, 1)),
        "stage_region_px": (round(stage_w, 1), round(stage_h, 1)),
    }


def get_text_bounding_boxes(
    spec: SimSpec,
    quality: str = "final",
) -> Dict[str, Tuple[float, float, float, float]]:
    """
    Calculates (x_min, y_min, x_max, y_max) for title, counter, and payoff text.
    """
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["final"])
    w, h = preset["width"], preset["height"]
    scale = w / 1080.0

    # Temporary context to measure text
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
    ctx = cairo.Context(surface)
    ctx.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)

    # 1. Title Bounding Box
    title_font_size = 60.0 * scale
    ctx.set_font_size(title_font_size)
    ext_title = ctx.text_extents(spec.title)

    title_cx = w / 2.0
    title_baseline_y = 360.0 * scale
    title_x0 = title_cx - ext_title.width / 2.0 - ext_title.x_bearing
    title_box = (
        title_x0 + ext_title.x_bearing,
        title_baseline_y + ext_title.y_bearing,
        title_x0 + ext_title.x_bearing + ext_title.width,
        title_baseline_y + ext_title.y_bearing + ext_title.height,
    )

    # 2. Counter Bounding Box
    max_count = max(s.count for s in spec.schedule) if spec.schedule else 55
    counter_text = f"{spec.counter_label}: {max_count}"
    counter_font_size = 48.0 * scale
    ctx.set_font_size(counter_font_size)
    ext_counter = ctx.text_extents(counter_text)

    counter_cx = w / 2.0
    counter_baseline_y = 430.0 * scale
    counter_x0 = counter_cx - ext_counter.width / 2.0 - ext_counter.x_bearing
    counter_box = (
        counter_x0 + ext_counter.x_bearing,
        counter_baseline_y + ext_counter.y_bearing,
        counter_x0 + ext_counter.x_bearing + ext_counter.width,
        counter_baseline_y + ext_counter.y_bearing + ext_counter.height,
    )

    boxes = {"title": title_box, "counter": counter_box}

    # 3. Payoff Text Bounding Box (if present)
    if spec.payoff_text:
        payoff_font_size = 36.0 * scale
        ctx.set_font_size(payoff_font_size)
        ext_payoff = ctx.text_extents(spec.payoff_text)
        payoff_cx = w / 2.0
        payoff_baseline_y = 1250.0 * scale
        payoff_x0 = payoff_cx - ext_payoff.width / 2.0 - ext_payoff.x_bearing
        boxes["payoff"] = (
            payoff_x0 + ext_payoff.x_bearing,
            payoff_baseline_y + ext_payoff.y_bearing,
            payoff_x0 + ext_payoff.x_bearing + ext_payoff.width,
            payoff_baseline_y + ext_payoff.y_bearing + ext_payoff.height,
        )

    return boxes


def is_bbox_inside_safe(bbox: Tuple[float, float, float, float], width: int, height: int) -> bool:
    """Checks if a bounding box (x_min, y_min, x_max, y_max) is completely inside the safe zone."""
    sx_min, sy_min, sx_max, sy_max = get_safe_area_bounds(width, height)
    bx_min, by_min, bx_max, by_max = bbox
    return (
        bx_min >= sx_min - 1.0
        and bx_max <= sx_max + 1.0
        and by_min >= sy_min - 1.0
        and by_max <= sy_max + 1.0
    )


class SimulationRenderer:
    """
    Renders frame-by-frame Cairo canvas and pipes raw video to FFmpeg.
    Optimized with static layer caching and half-resolution glow bloom.
    """

    def __init__(self, spec: SimSpec, quality: str = "test"):
        self.spec = spec
        self.quality = quality
        preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["test"])
        self.width = preset["width"]
        self.height = preset["height"]
        self.fps = preset["fps"]
        self.scale = self.width / 1080.0

        # Stage geometry from LAYOUT_916
        stage_cx, stage_cy, stage_w, stage_h = get_stage_region_bounds(self.width, self.height)
        self.center_x = stage_cx
        self.center_y = stage_cy

        # Scale ellipse to fill ~92% of stage region (height is limiting: 0.92 * stage_h)
        scale_w = (0.92 * stage_w) / (2.0 * self.spec.ellipse.a)
        scale_h = (0.92 * stage_h) / (2.0 * self.spec.ellipse.b)
        self.sim_scale = min(scale_w, scale_h)

        # Ellipse pixel radii
        self.ellipse_rx = self.spec.ellipse.a * self.sim_scale
        self.ellipse_ry = self.spec.ellipse.b * self.sim_scale

        # Precalculate stage timing index
        self.stages_timing: List[Tuple[float, float, int]] = []
        cum_t = 0.0
        for s in self.spec.schedule:
            self.stages_timing.append((cum_t, cum_t + s.duration_sec, s.count))
            cum_t += s.duration_sec
        self.total_duration = cum_t

        # Half-resolution dimensions for 5x faster glow processing
        self.glow_w = max(64, self.width // 2)
        self.glow_h = max(64, self.height // 2)
        self.glow_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.glow_w, self.glow_h)

        # 1. Pre-render Static Layer (background vignette, ellipse fill, neon stroke, baseline foci)
        self.static_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        self._prerender_static_layer()

    def _prerender_static_layer(self) -> None:
        """Pre-renders static background and ellipse architecture once to avoid per-frame overhead."""
        ctx = cairo.Context(self.static_surface)

        # Background with soft radial vignette
        grad = cairo.RadialGradient(
            self.center_x, self.center_y, 0.25 * self.width,
            self.center_x, self.center_y, 0.85 * self.height,
        )
        grad.add_color_stop_rgb(0.0, *COLOR_BACKGROUND)
        grad.add_color_stop_rgb(1.0, *COLOR_BACKGROUND_DARK)
        ctx.set_source(grad)
        ctx.paint()

        # Faint inner ellipse fill
        ctx.save()
        ctx.translate(self.center_x, self.center_y)
        ctx.scale(self.ellipse_rx, self.ellipse_ry)
        ctx.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
        ctx.restore()

        # Inner subtle tinted glass fill
        ctx.set_source_rgba(COLOR_ELLIPSE[0], COLOR_ELLIPSE[1], COLOR_ELLIPSE[2], 0.04)
        ctx.fill_preserve()

        # Neon Glow around Ellipse outline
        # Outer soft glow pass
        ctx.set_source_rgba(COLOR_ELLIPSE[0], COLOR_ELLIPSE[1], COLOR_ELLIPSE[2], 0.20)
        ctx.set_line_width(max(12.0 * self.scale, 4.0))
        ctx.stroke_preserve()

        # Mid glow pass
        ctx.set_source_rgba(COLOR_ELLIPSE[0], COLOR_ELLIPSE[1], COLOR_ELLIPSE[2], 0.45)
        ctx.set_line_width(max(8.0 * self.scale, 3.0))
        ctx.stroke_preserve()

        # Crisp primary outline (>= 5px wide at 1080px width)
        line_w = max(5.0 * self.scale, 2.0)
        ctx.set_source_rgb(*COLOR_ELLIPSE)
        ctx.set_line_width(line_w)
        ctx.stroke()

        # Baseline Foci markers (static core)
        c_val = self.spec.ellipse.c
        f1_px = self.sim_to_pixel((0.0, -c_val))
        f2_px = self.sim_to_pixel((0.0, c_val))

        for f_pos in (f1_px, f2_px):
            # Outer halo
            ctx.set_source_rgba(COLOR_ELLIPSE[0], COLOR_ELLIPSE[1], COLOR_ELLIPSE[2], 0.35)
            ctx.arc(f_pos[0], f_pos[1], max(6.0 * self.scale, 2.5), 0.0, 2.0 * math.pi)
            ctx.fill()
            # Inner bright center
            ctx.set_source_rgb(1.0, 1.0, 1.0)
            ctx.arc(f_pos[0], f_pos[1], max(2.5 * self.scale, 1.2), 0.0, 2.0 * math.pi)
            ctx.fill()

    def sim_to_pixel(self, p: Tuple[float, float]) -> Tuple[float, float]:
        """Converts math simulation (x, y) coordinates to Cairo screen pixels."""
        px = self.center_x + p[0] * self.sim_scale
        py = self.center_y - p[1] * self.sim_scale
        return (px, py)

    def get_stage_info_at(self, t: float) -> Tuple[int, int, float, float]:
        """Returns (stage_idx, count, stage_start, stage_end) for time t."""
        for idx, (t0, t1, count) in enumerate(self.stages_timing):
            if t0 <= t < t1 or idx == len(self.stages_timing) - 1:
                return (idx, count, t0, t1)
        return (0, 1, 0.0, 2.0)

    def render_frame_into(
        self,
        surface: cairo.ImageSurface,
        t: float,
        events: List[SimEvent],
    ) -> None:
        """Renders one complete frame at timestamp t into the provided Cairo ImageSurface."""
        ctx = cairo.Context(surface)

        # 1. Blit cached static background & ellipse layer (< 1ms)
        ctx.set_source_surface(self.static_surface, 0, 0)
        ctx.paint()

        stage_idx, count, stage_t0, stage_t1 = self.get_stage_info_at(t)

        # 2. Foci dynamic pulses
        # F1 launch pulse at stage start (t_stage)
        dt_launch = t - stage_t0
        if 0.0 <= dt_launch < 0.45:
            pulse = math.exp(-dt_launch / 0.12)
            c_val = self.spec.ellipse.c
            f1_px = self.sim_to_pixel((0.0, -c_val))
            ctx.set_source_rgba(COLOR_BALL_BLUE[0], COLOR_BALL_BLUE[1], COLOR_BALL_BLUE[2], 0.6 * pulse)
            ctx.arc(f1_px[0], f1_px[1], (12.0 + 35.0 * dt_launch) * self.scale, 0.0, 2.0 * math.pi)
            ctx.fill()

        # F2 focal convergence ring pulse at t = stage_t0 + 2*b
        t_conv = stage_t0 + 2.0 * self.spec.ellipse.b
        dt_conv = t - t_conv
        if 0.0 <= dt_conv < 0.50:
            ring_alpha = 0.85 * math.exp(-dt_conv / 0.15)
            ring_r = (8.0 + 75.0 * dt_conv) * self.scale
            c_val = self.spec.ellipse.c
            f2_px = self.sim_to_pixel((0.0, c_val))
            ctx.set_source_rgba(COLOR_ELLIPSE[0], COLOR_ELLIPSE[1], COLOR_ELLIPSE[2], ring_alpha)
            ctx.set_line_width(max(3.5 * self.scale, 1.5))
            ctx.arc(f2_px[0], f2_px[1], ring_r, 0.0, 2.0 * math.pi)
            ctx.stroke()

        # 3. Balls & Fading Motion Trails
        # Longer, brighter fading trails
        trail_duration = 0.50  # 500 ms history
        num_steps = 18
        step_dt = trail_duration / num_steps

        # Clear half-resolution glow surface
        glow_ctx = cairo.Context(self.glow_surface)
        glow_ctx.save()
        glow_ctx.set_operator(cairo.OPERATOR_CLEAR)
        glow_ctx.paint()
        glow_ctx.restore()
        # Scale glow context to half resolution (0.5x)
        glow_ctx.scale(0.5, 0.5)

        # Ball diameter >= 14px at 1080px width
        ball_r = max(7.0 * self.scale, 2.5)

        for ball_id in range(count):
            ball_color = get_ball_color(ball_id, count)

            # Draw trail segments
            trail_pts: List[Tuple[float, float]] = []
            for k in range(num_steps + 1):
                past_t = t - k * step_dt
                if past_t < stage_t0:
                    break
                p_sim = get_ball_position_at(events, ball_id, past_t)
                if p_sim is not None:
                    trail_pts.append(self.sim_to_pixel(p_sim))

            if len(trail_pts) >= 2:
                for k in range(len(trail_pts) - 1):
                    alpha = ((1.0 - k / float(num_steps)) ** 1.3) * 0.70
                    ctx.set_source_rgba(ball_color[0], ball_color[1], ball_color[2], alpha)
                    ctx.set_line_width((ball_r * 1.6) * (1.0 - k / float(num_steps)) + 1.0 * self.scale)
                    ctx.move_to(trail_pts[k][0], trail_pts[k][1])
                    ctx.line_to(trail_pts[k + 1][0], trail_pts[k + 1][1])
                    ctx.stroke()

            # Current ball head
            curr_sim = get_ball_position_at(events, ball_id, t)
            if curr_sim is not None:
                px, py = self.sim_to_pixel(curr_sim)

                # Draw on half-resolution glow surface
                glow_ctx.set_source_rgba(ball_color[0], ball_color[1], ball_color[2], 0.90)
                glow_ctx.arc(px, py, ball_r * 2.5, 0.0, 2.0 * math.pi)
                glow_ctx.fill()

                # Draw crisp ball body on main surface
                # Outer color disk
                ctx.set_source_rgb(*ball_color)
                ctx.arc(px, py, ball_r, 0.0, 2.0 * math.pi)
                ctx.fill()

                # Inner specular highlight core
                ctx.set_source_rgb(1.0, 1.0, 1.0)
                ctx.arc(px, py, ball_r * 0.5, 0.0, 2.0 * math.pi)
                ctx.fill()

        # 4. Composite Half-Resolution Gaussian Bloom
        glow_data = np.frombuffer(self.glow_surface.get_data(), np.uint8).reshape(self.glow_h, self.glow_w, 4)
        if glow_data.max() > 0:
            sigma = max(1.2, 2.8 * self.scale)
            blurred = scipy.ndimage.gaussian_filter(glow_data.astype(np.float32), sigma=(sigma, sigma, 0))
            blurred_uint8 = np.clip(blurred, 0, 255).astype(np.uint8)

            blurred_surface = cairo.ImageSurface.create_for_data(
                blurred_uint8, cairo.FORMAT_ARGB32, self.glow_w, self.glow_h
            )
            ctx.save()
            ctx.scale(2.0, 2.0)  # Upscale 2x back to full canvas
            ctx.set_operator(cairo.OPERATOR_ADD)
            ctx.set_source_surface(blurred_surface, 0, 0)
            ctx.paint()
            ctx.restore()

        # 5. Typography: Title & Counter
        ctx.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)

        # Title
        title_font_size = 60.0 * self.scale
        ctx.set_font_size(title_font_size)
        ext_title = ctx.text_extents(self.spec.title)
        title_x = self.center_x - ext_title.width / 2.0 - ext_title.x_bearing
        title_y = 360.0 * self.scale

        ctx.set_source_rgb(*COLOR_TEXT_PRIMARY)
        ctx.move_to(title_x, title_y)
        ctx.show_text(self.spec.title)

        # Counter: "Balls: N"
        counter_str = f"{self.spec.counter_label}: {count}"
        counter_font_size = 48.0 * self.scale
        ctx.set_font_size(counter_font_size)
        ext_counter = ctx.text_extents(counter_str)
        counter_x = self.center_x - ext_counter.width / 2.0 - ext_counter.x_bearing
        counter_y = 430.0 * self.scale

        ctx.set_source_rgb(*COLOR_TEXT_COUNTER)
        ctx.move_to(counter_x, counter_y)
        ctx.show_text(counter_str)

        # 6. Payoff Text: Fades in during the last 4 seconds inside caption region
        if self.spec.payoff_text and t >= max(0.0, self.total_duration - 4.0):
            fade_in = min(1.0, (t - (self.total_duration - 4.0)) / 1.0)
            payoff_font_size = 36.0 * self.scale
            ctx.set_font_size(payoff_font_size)
            ext_payoff = ctx.text_extents(self.spec.payoff_text)

            payoff_x = self.center_x - ext_payoff.width / 2.0 - ext_payoff.x_bearing
            payoff_y = 1250.0 * self.scale  # Inside LAYOUT_916 caption region (safe, above bottom 1440px)

            # Soft dark translucent pill backplate for contrast > 4.5
            pad_x = 24.0 * self.scale
            pad_y = 14.0 * self.scale
            ctx.set_source_rgba(10 / 255.0, 10 / 255.0, 14 / 255.0, 0.75 * fade_in)
            ctx.rectangle(
                payoff_x + ext_payoff.x_bearing - pad_x,
                payoff_y + ext_payoff.y_bearing - pad_y,
                ext_payoff.width + 2.0 * pad_x,
                ext_payoff.height + 2.0 * pad_y,
            )
            ctx.fill()

            # Text
            ctx.set_source_rgba(1.0, 1.0, 1.0, fade_in)
            ctx.move_to(payoff_x, payoff_y)
            ctx.show_text(self.spec.payoff_text)


def render_simulation_video(
    spec: SimSpec,
    output_path: Union[str, Path],
    quality: str = "test",
    max_duration: Optional[float] = None,
    events: Optional[List[SimEvent]] = None,
    progress_callback: Optional[callable] = None,
) -> Path:
    """
    Renders video by piping Cairo frames directly into FFmpeg stdin.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    renderer = SimulationRenderer(spec, quality=quality)
    w, h, fps = renderer.width, renderer.height, renderer.fps

    sim = EllipseBilliardsSim(axes=spec.ellipse, seed=spec.seed)
    if events is None:
        events = sim.simulate_spec(spec)

    total_time = max_duration if max_duration is not None else renderer.total_duration
    total_frames = int(math.ceil(total_time * fps))

    # Spawn FFmpeg with rawvideo pipe
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{w}x{h}",
        "-pix_fmt", "bgra",
        "-r", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        "-preset", "fast",
        str(out_file),
    ]

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)

    try:
        for f_idx in range(total_frames):
            t_curr = f_idx / float(fps)
            renderer.render_frame_into(surface, t_curr, events)
            # Pipe frame data directly
            proc.stdin.write(surface.get_data())

            if progress_callback and (f_idx % 30 == 0 or f_idx == total_frames - 1):
                progress_callback(f_idx + 1, total_frames)

        proc.stdin.close()
        proc.wait()

    except Exception:
        proc.kill()
        raise

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg encoding failed with exit code {proc.returncode}")

    return out_file
