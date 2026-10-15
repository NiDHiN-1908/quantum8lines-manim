"""
Exact, deterministic ellipse billiards simulation.
Follows Milestone P1 Step 1.
Computes ray-ellipse intersections and specular reflections analytically (no numerical time-stepping).
All balls launched from focus F1 reach focus F2 at exactly t_launch + 2*b.
"""

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from core.sims.sound.models import SoundPaletteSpec


class EventKind(str, Enum):
    LAUNCH = "launch"
    BOUNCE = "bounce"
    PASS_FOCUS = "pass_focus"


class SimEvent(BaseModel):
    """Event emitted during an ellipse billiards trajectory."""
    time: float
    ball_id: int
    point: Tuple[float, float]
    kind: EventKind
    velocity: Optional[Tuple[float, float]] = None
    normal: Optional[Tuple[float, float]] = None


class EllipseAxes(BaseModel):
    """Semi-minor (a) and semi-major (b) axes of the ellipse."""
    a: float = 0.6  # horizontal semi-minor axis
    b: float = 0.8  # vertical semi-major axis (foci on vertical y-axis)

    @property
    def c(self) -> float:
        """Focal distance from center along the y-axis."""
        if self.b <= self.a:
            raise ValueError(f"Vertical ellipse requires b > a (got a={self.a}, b={self.b})")
        return math.sqrt(self.b**2 - self.a**2)

    @property
    def f1(self) -> Tuple[float, float]:
        """Launch focus F1 on negative y-axis."""
        return (0.0, -self.c)

    @property
    def f2(self) -> Tuple[float, float]:
        """Target focus F2 on positive y-axis."""
        return (0.0, self.c)


class StageSpec(BaseModel):
    """Specification for one ball-count stage."""
    count: int
    duration_sec: float = 3.5


class SoundSettings(BaseModel):
    """Sound synthesis configuration for procedural audio."""
    sample_rate: int = 48000
    base_freq: float = 261.63  # C4
    scale_semitones: List[int] = Field(default_factory=lambda: [0, 2, 4, 7, 9])  # Major pentatonic scale
    ping_decay_sec: float = 0.08
    chime_freq: float = 523.25  # C5 chime at focus convergence
    chime_decay_sec: float = 0.35
    pad_enabled: bool = True
    pad_gain: float = 0.08


class SimSpec(BaseModel):
    """Full simulation specification for ellipse billiards short."""
    title: str = "Where do they all meet?"
    counter_label: str = "Balls"
    ellipse: EllipseAxes = Field(default_factory=EllipseAxes)
    schedule: List[StageSpec] = Field(
        default_factory=lambda: [
            StageSpec(count=1, duration_sec=2.0),
            StageSpec(count=2, duration_sec=2.0),
            StageSpec(count=3, duration_sec=2.5),
            StageSpec(count=5, duration_sec=3.0),
            StageSpec(count=8, duration_sec=3.5),
            StageSpec(count=13, duration_sec=4.0),
            StageSpec(count=21, duration_sec=4.5),
            StageSpec(count=34, duration_sec=5.0),
            StageSpec(count=55, duration_sec=5.5),
        ]
    )
    payoff_text: Optional[str] = "Every ray from one focus passes through the other."
    seed: int = 42
    sound: SoundSettings = Field(default_factory=SoundSettings)
    sound_palette: Optional["SoundPaletteSpec"] = None

    @property
    def total_duration(self) -> float:
        return sum(s.duration_sec for s in self.schedule)


class EllipseBilliardsSim:
    """
    Exact analytical simulation engine for ellipse billiards.
    """

    def __init__(self, axes: Optional[EllipseAxes] = None, seed: int = 42):
        self.axes = axes or EllipseAxes()
        self.seed = seed
        self.a = self.axes.a
        self.b = self.axes.b
        self.c = self.axes.c
        self.f1 = self.axes.f1
        self.f2 = self.axes.f2

    def ray_ellipse_intersection(
        self,
        p0: Tuple[float, float],
        d: Tuple[float, float],
        is_on_boundary: bool = False,
    ) -> Tuple[float, Tuple[float, float], Tuple[float, float]]:
        """
        Solves ray-ellipse intersection exactly.
        Returns:
            distance t > 0
            intersection point (x, y)
            inward unit normal vector (nx, ny)
        """
        x0, y0 = p0
        dx, dy = d
        inv_a2 = 1.0 / (self.a**2)
        inv_b2 = 1.0 / (self.b**2)

        A = (dx**2) * inv_a2 + (dy**2) * inv_b2
        B = 2.0 * (x0 * dx * inv_a2 + y0 * dy * inv_b2)
        C = (x0**2) * inv_a2 + (y0**2) * inv_b2 - 1.0

        if is_on_boundary:
            # Point is already on boundary (C ~= 0). The positive root is -B/A (since B < 0 for inward ray)
            t = -B / A
            if t <= 1e-12:
                # Numerical safeguard
                disc = max(0.0, B**2 - 4.0 * A * C)
                t = (-B + math.sqrt(disc)) / (2.0 * A)
        else:
            disc = max(0.0, B**2 - 4.0 * A * C)
            t = (-B + math.sqrt(disc)) / (2.0 * A)

        p_hit = (x0 + t * dx, y0 + t * dy)

        # Inward normal at p_hit:
        # Gradient of f(x, y) = (x/a)^2 + (y/b)^2 - 1 is (2x/a^2, 2y/b^2)
        grad_x = 2.0 * p_hit[0] * inv_a2
        grad_y = 2.0 * p_hit[1] * inv_b2
        g_len = math.hypot(grad_x, grad_y)
        inward_normal = (-grad_x / g_len, -grad_y / g_len)

        return t, p_hit, inward_normal

    def reflect(
        self,
        d_in: Tuple[float, float],
        normal_in: Tuple[float, float],
        perturbed_normal: Optional[Tuple[float, float]] = None,
    ) -> Tuple[float, float]:
        """
        Reflects incoming velocity d_in using the inward unit normal.
        d_out = d_in - 2 * (d_in . n) * n
        """
        n = perturbed_normal if perturbed_normal is not None else normal_in
        dot = d_in[0] * n[0] + d_in[1] * n[1]
        rx = d_in[0] - 2.0 * dot * n[0]
        ry = d_in[1] - 2.0 * dot * n[1]
        r_len = math.hypot(rx, ry)
        return (rx / r_len, ry / r_len)

    def simulate_ball(
        self,
        ball_id: int,
        start_time: float,
        angle: float,
        duration: float,
        perturbed_bounce: Optional[int] = None,
        perturbation_rad: float = 0.05,
    ) -> List[SimEvent]:
        """
        Simulates a single ball launched from F1 at start_time for a total time of duration.
        Generates:
        - Launch event at start_time from F1
        - Bounce events at each wall reflection
        - Pass focus events at each focal convergence
        """
        events: List[SimEvent] = []
        curr_time = start_time
        max_time = start_time + duration

        curr_pos = self.f1
        vel = (math.cos(angle), math.sin(angle))

        # Launch event
        events.append(
            SimEvent(
                time=curr_time,
                ball_id=ball_id,
                point=curr_pos,
                kind=EventKind.LAUNCH,
                velocity=vel,
            )
        )

        bounce_count = 0
        is_on_boundary = False

        while curr_time < max_time - 1e-9:
            # Next ray-ellipse intersection
            dist_to_wall, p_wall, normal = self.ray_ellipse_intersection(
                curr_pos, vel, is_on_boundary=is_on_boundary
            )

            # Target focus for this pass
            # After bounce 0 (launch from F1), passes through F2.
            # After bounce 1 (reflected from wall), passes through F2.
            # After bounce 2, passes through F1.
            # In general, if coming from bounce k >= 1:
            # odd bounce k -> passes F2
            # even bounce k -> passes F1
            target_focus = self.f2 if (bounce_count % 2 == 1) else None

            # Check if focus is traversed on this segment (for bounce_count >= 1)
            if target_focus is not None:
                # Vector from curr_pos to target_focus
                v_f = (target_focus[0] - curr_pos[0], target_focus[1] - curr_pos[1])
                dist_to_focus = math.hypot(v_f[0], v_f[1])
                # Check if target focus lies forward along the ray before the wall
                dot_f = v_f[0] * vel[0] + v_f[1] * vel[1]
                if dot_f > 0 and abs(dist_to_focus - dot_f) < 1e-9 and dist_to_focus < dist_to_wall:
                    time_at_focus = curr_time + dist_to_focus
                    if time_at_focus <= max_time:
                        events.append(
                            SimEvent(
                                time=time_at_focus,
                                ball_id=ball_id,
                                point=target_focus,
                                kind=EventKind.PASS_FOCUS,
                                velocity=vel,
                            )
                        )

            time_at_wall = curr_time + dist_to_wall
            if time_at_wall > max_time:
                # Segment reaches past max_time; no more wall bounces in window
                break

            bounce_count += 1
            curr_time = time_at_wall
            curr_pos = p_wall
            is_on_boundary = True

            # Reflection with optional seeded perturbation
            eff_normal = normal
            if perturbed_bounce is not None and bounce_count == perturbed_bounce:
                cos_p = math.cos(perturbation_rad)
                sin_p = math.sin(perturbation_rad)
                eff_normal = (
                    normal[0] * cos_p - normal[1] * sin_p,
                    normal[0] * sin_p + normal[1] * cos_p,
                )

            vel = self.reflect(vel, normal, perturbed_normal=eff_normal if eff_normal != normal else None)

            events.append(
                SimEvent(
                    time=curr_time,
                    ball_id=ball_id,
                    point=curr_pos,
                    kind=EventKind.BOUNCE,
                    velocity=vel,
                    normal=normal,
                )
            )

        events.sort(key=lambda e: (e.time, e.kind.value))
        return events

    def simulate_stage(
        self,
        count: int,
        start_time: float,
        duration: float,
        stage_idx: int = 0,
    ) -> List[SimEvent]:
        """
        Simulates count balls launched simultaneously from F1 at start_time.
        Angles are spread evenly over [0, 2*pi).
        """
        all_events: List[SimEvent] = []
        # Base offset to make fan asymmetric and visually appealing
        angle_offset = (math.pi / 4.0) + (self.seed * 0.1337)
        for i in range(count):
            angle = angle_offset + (2.0 * math.pi * i) / count
            ball_events = self.simulate_ball(
                ball_id=i,
                start_time=start_time,
                angle=angle,
                duration=duration,
            )
            all_events.extend(ball_events)

        all_events.sort(key=lambda e: (e.time, e.ball_id, e.kind.value))
        return all_events

    def simulate_spec(self, spec: SimSpec) -> List[SimEvent]:
        """Runs the entire schedule from a SimSpec."""
        all_events: List[SimEvent] = []
        curr_time = 0.0
        for idx, stage in enumerate(spec.schedule):
            stage_events = self.simulate_stage(
                count=stage.count,
                start_time=curr_time,
                duration=stage.duration_sec,
                stage_idx=idx,
            )
            all_events.extend(stage_events)
            curr_time += stage.duration_sec

        all_events.sort(key=lambda e: (e.time, e.ball_id, e.kind.value))
        return all_events


def get_ball_position_at(
    events: List[SimEvent],
    ball_id: int,
    t: float,
) -> Optional[Tuple[float, float]]:
    """
    Interpolates exact (x, y) coordinates for a ball at time t from its events.
    """
    ball_events = [e for e in events if e.ball_id == ball_id]
    if not ball_events:
        return None

    # Filter out redundant events at exact same time if any
    unique_events: List[SimEvent] = []
    for e in ball_events:
        if not unique_events or abs(e.time - unique_events[-1].time) > 1e-12:
            unique_events.append(e)

    if t < unique_events[0].time:
        return None
    if t >= unique_events[-1].time:
        # Extrapolate along last velocity or hold position
        last = unique_events[-1]
        if last.velocity is not None:
            dt = t - last.time
            return (last.point[0] + dt * last.velocity[0], last.point[1] + dt * last.velocity[1])
        return last.point

    # Binary search or scan for segment
    for i in range(len(unique_events) - 1):
        e1 = unique_events[i]
        e2 = unique_events[i + 1]
        if e1.time <= t <= e2.time:
            dt_segment = e2.time - e1.time
            if dt_segment < 1e-12:
                return e1.point
            frac = (t - e1.time) / dt_segment
            x = e1.point[0] + frac * (e2.point[0] - e1.point[0])
            y = e1.point[1] + frac * (e2.point[1] - e1.point[1])
            return (x, y)

    return unique_events[-1].point
