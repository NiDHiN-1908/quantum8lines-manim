"""
Fast frame-by-frame renderer for ellipse billiards using pycairo + numpy + FFmpeg.
Follows Milestone P1 Step 2.
- Direct pycairo rasterization without Manim runtime overhead.
- Gaussian glow bloom via scipy.ndimage.
- Fading motion trails.
- Brand tokens: BACKGROUND (#0e0e11), PRIMARY (#58c4dd), blue-to-orange ball gradient.
- Frame pipe to ffmpeg (libx264, yuv420p, 30 fps).
- Strict safe area compliance (LAYOUT_916).
"""

import math
from pathlib import Path
import subprocess
import time
from typing import Dict, List, Optional, Tuple, Union

import cairo
import numpy as np
import scipy.ndimage

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
COLOR_ELLIPSE = (88 / 255.0, 196 / 255.0, 221 / 255.0)        # PRIMARY (#58c4dd)
COLOR_TEXT_PRIMARY = (1.0, 1.0, 1.0)                          # White (#ffffff)
COLOR_TEXT_COUNTER = (0.95, 0.82, 0.30)                       # Warm golden yellow
COLOR_BALL_BLUE = (88 / 255.0, 196 / 255.0, 221 / 255.0)      # Gradient start
COLOR_BALL_ORANGE = (250 / 255.0, 132 / 255.0, 20 / 255.0)    # Gradient end


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


def get_text_bounding_boxes(
    spec: SimSpec,
    quality: str = "final",
) -> Dict[str, Tuple[float, float, float, float]]:
    """
    Calculates (x_min, y_min, x_max, y_max) for title and counter text.
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

    # 2. Counter Bounding Box (worst-case label with max count)
    max_count = max(s.count for s in spec.schedule) if spec.schedule else 55
    counter_text = f"{spec.counter_label}: {max_count}"
    counter_font_size = 48.0 * scale  # SPEC 4.3 label minimum 48px
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

    return {"title": title_box, "counter": counter_box}


def is_bbox_inside_safe(bbox: Tuple[float, float, float, float], width: int, height: int) -> bool:
    """Checks if a bounding box (x_min, y_min, x_max, y_max) is completely inside the safe zone."""
    sx_min, sy_min, sx_max, sy_max = get_safe_area_bounds(width, height)
    bx_min, by_min, bx_max, by_max = bbox
    return (
        bx_min >= sx_min - 1e-3
        and bx_max <= sx_max + 1e-3
        and by_min >= sy_min - 1e-3
        and by_max <= sy_max + 1e-3
    )


class SimulationRenderer:
    """Renders frame-by-frame Cairo canvas and pipes raw video to FFmpeg."""

    def __init__(self, spec: SimSpec, quality: str = "test"):
        self.spec = spec
        self.quality = quality
        preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["test"])
        self.width = preset["width"]
        self.height = preset["height"]
        self.fps = preset["fps"]
        self.scale = self.width / 1080.0

        # Stage geometry in pixel space
        # Center of stage region in 9:16 layout
        self.center_x = self.width / 2.0
        self.center_y = 800.0 * self.scale
        # Scaling factor from sim coordinates to pixel coordinates
        self.sim_scale = 320.0 * self.scale

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

    def sim_to_pixel(self, p: Tuple[float, float]) -> Tuple[float, float]:
        """Converts math simulation (x, y) coordinates to Cairo screen pixels."""
        # y axis in math points up, in screen points down
        px = self.center_x + p[0] * self.sim_scale
        py = self.center_y - p[1] * self.sim_scale
        return (px, py)

    def get_stage_info_at(self, t: float) -> Tuple[int, int, float, float]:
        """Returns (stage_idx, count, stage_start, stage_end) for time t."""
        for idx, (t0, t1, count) in enumerate(self.stages_timing):
            if t0 <= t < t1 or idx == len(self.stages_timing) - 1:
                return (idx, count, t0, t1)
        return (0, 1, 0.0, 3.5)

    def render_frame_into(
        self,
        surface: cairo.ImageSurface,
        t: float,
        events: List[SimEvent],
    ) -> None:
        """Renders one complete frame at timestamp t into the provided Cairo ImageSurface."""
        ctx = cairo.Context(surface)

        # 1. Background fill
        ctx.set_source_rgb(*COLOR_BACKGROUND)
        ctx.paint()

        # 2. Draw Ellipse boundary & Foci
        ctx.save()
        ctx.translate(self.center_x, self.center_y)
        ctx.scale(self.ellipse_rx, self.ellipse_ry)
        ctx.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
        ctx.restore()

        # Fill subtle dark interior
        ctx.set_source_rgba(0.08, 0.09, 0.13, 0.7)
        ctx.fill_preserve()

        # Stroke primary glowing boundary
        ctx.set_source_rgb(*COLOR_ELLIPSE)
        ctx.set_line_width(2.5 * self.scale)
        ctx.stroke()

        # Draw Foci points
        c_val = self.spec.ellipse.c
        f1_px = self.sim_to_pixel((0.0, -c_val))
        f2_px = self.sim_to_pixel((0.0, c_val))

        for f_pos in (f1_px, f2_px):
            # Outer halo
            ctx.set_source_rgba(COLOR_ELLIPSE[0], COLOR_ELLIPSE[1], COLOR_ELLIPSE[2], 0.25)
            ctx.arc(f_pos[0], f_pos[1], 5.0 * self.scale, 0.0, 2.0 * math.pi)
            ctx.fill()
            # Inner bright center
            ctx.set_source_rgb(*COLOR_ELLIPSE)
            ctx.arc(f_pos[0], f_pos[1], 2.0 * self.scale, 0.0, 2.0 * math.pi)
            ctx.fill()

        # 3. Determine current stage and active balls
        stage_idx, count, stage_t0, stage_t1 = self.get_stage_info_at(t)

        # 4. Fading Motion Trails
        trail_duration = 0.35  # seconds of history
        num_steps = 14
        step_dt = trail_duration / num_steps

        # Create separate surface for glow pass
        glow_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        glow_ctx = cairo.Context(glow_surface)

        for ball_id in range(count):
            ball_color = get_ball_color(ball_id, count)
            ball_r = max(2.5 * self.scale, 1.5)

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
                    alpha = (1.0 - k / float(num_steps)) ** 1.8 * 0.55
                    ctx.set_source_rgba(ball_color[0], ball_color[1], ball_color[2], alpha)
                    ctx.set_line_width((ball_r * 1.5) * (1.0 - k / float(num_steps)) + 0.5)
                    ctx.move_to(trail_pts[k][0], trail_pts[k][1])
                    ctx.line_to(trail_pts[k + 1][0], trail_pts[k + 1][1])
                    ctx.stroke()

            # Current ball head
            curr_sim = get_ball_position_at(events, ball_id, t)
            if curr_sim is not None:
                px, py = self.sim_to_pixel(curr_sim)
                # Draw on glow surface
                glow_ctx.set_source_rgba(ball_color[0], ball_color[1], ball_color[2], 0.85)
                glow_ctx.arc(px, py, ball_r * 2.2, 0.0, 2.0 * math.pi)
                glow_ctx.fill()

                # Draw solid ball core on main context
                ctx.set_source_rgb(1.0, 1.0, 1.0)
                ctx.arc(px, py, ball_r * 0.7, 0.0, 2.0 * math.pi)
                ctx.fill()

                ctx.set_source_rgb(*ball_color)
                ctx.arc(px, py, ball_r, 0.0, 2.0 * math.pi)
                ctx.fill()

        # 5. Composite Gaussian Glow
        # Extract glow pixels as float numpy array, apply Gaussian blur, blend back
        glow_data = np.frombuffer(glow_surface.get_data(), np.uint8).reshape(self.height, self.width, 4)
        if glow_data.max() > 0:
            sigma = max(1.5, 3.5 * self.scale)
            blurred = scipy.ndimage.gaussian_filter(glow_data.astype(np.float32), sigma=(sigma, sigma, 0))
            blurred_uint8 = np.clip(blurred, 0, 255).astype(np.uint8)

            blurred_surface = cairo.ImageSurface.create_for_data(
                blurred_uint8, cairo.FORMAT_ARGB32, self.width, self.height
            )
            ctx.set_operator(cairo.OPERATOR_ADD)
            ctx.set_source_surface(blurred_surface, 0, 0)
            ctx.paint()
            ctx.set_operator(cairo.OPERATOR_OVER)

        # 6. Typography: Title & Counter
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
