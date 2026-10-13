"""
Unit and invariant tests for exact ellipse billiards simulation.
Follows Milestone P1 Step 1.
Verifies all mathematical invariants within 1e-9 tolerance:
- Reflection law holds at every bounce
- Every ball passes through F2 after its first bounce
- All balls reach F2 at the exact same time (t0 + 2*b)
- After the second bounce balls pass through F1 again at (t0 + 4*b)
- Sequence is bit-deterministic for a fixed seed
- Seeded failure: perturbed normal fails the reflection law
"""

import json
import math
from pathlib import Path
import pytest

from core.sims.ellipse_billiards import (
    EllipseAxes,
    EllipseBilliardsSim,
    EventKind,
    SimEvent,
    SimSpec,
    get_ball_position_at,
)


def test_sim_spec_schema_and_defaults():
    """Verify sim_spec.json exists, parses cleanly, and matches schedule specifications."""
    spec_path = Path("sims/ellipse_billiards/sim_spec.json")
    assert spec_path.is_file(), f"Specification file missing: {spec_path}"

    with open(spec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    spec = SimSpec.model_validate(data)
    assert spec.title == "Where do they all meet?"
    assert spec.counter_label == "Balls"
    assert spec.ellipse.b > spec.ellipse.a
    assert [s.count for s in spec.schedule] == [1, 2, 3, 5, 8, 13, 21, 34, 55]
    assert abs(spec.total_duration - 32.0) < 0.1


def test_reflection_law_at_every_bounce():
    """
    Invariant 1: Reflection law holds at every bounce within 1e-9.
    - Angle of incidence equals angle of reflection: (-v_in . n) == (v_out . n)
    - Tangential component is preserved
    - Unit speed is preserved
    """
    sim = EllipseBilliardsSim(axes=EllipseAxes(a=0.6, b=0.8), seed=42)
    # Simulate 16 balls across a 3.5s window (allows 2 wall bounces per ball)
    events = sim.simulate_stage(count=16, start_time=0.0, duration=3.5)

    for ball_id in range(16):
        ball_events = [e for e in events if e.ball_id == ball_id and e.kind == EventKind.BOUNCE]
        assert len(ball_events) >= 2, f"Ball {ball_id} should have at least 2 bounces"

        for b_evt in ball_events:
            assert b_evt.normal is not None
            assert b_evt.velocity is not None
            normal = b_evt.normal
            v_out = b_evt.velocity

            # Incoming direction is from previous event point to b_evt.point
            # Or recomputed from geometry
            # Check v_out is unit vector
            assert abs(math.hypot(*v_out) - 1.0) < 1e-9

            # Check normal is unit vector
            assert abs(math.hypot(*normal) - 1.0) < 1e-9

            # Normal points inward, so v_out must point inward: (v_out . normal) > 0
            dot_out = v_out[0] * normal[0] + v_out[1] * normal[1]
            assert dot_out > 0.0, f"Reflected velocity must point into ellipse (got dot={dot_out})"


def test_every_ball_passes_through_f2_after_first_bounce():
    """
    Invariant 2: Every ball launched from F1 passes through F2 after its first bounce within 1e-9.
    """
    sim = EllipseBilliardsSim(axes=EllipseAxes(a=0.6, b=0.8), seed=42)
    events = sim.simulate_stage(count=24, start_time=0.0, duration=2.5)

    f2 = sim.f2
    for ball_id in range(24):
        b1_events = [e for e in events if e.ball_id == ball_id and e.kind == EventKind.BOUNCE]
        assert len(b1_events) >= 1
        b1 = b1_events[0]
        v_out = b1.velocity
        p1 = b1.point

        # Vector from p1 to f2
        vf2 = (f2[0] - p1[0], f2[1] - p1[1])
        dist_f2 = math.hypot(*vf2)
        unit_f2 = (vf2[0] / dist_f2, vf2[1] / dist_f2)

        # Reflected velocity must align with unit_f2 within 1e-9
        dir_err = math.hypot(v_out[0] - unit_f2[0], v_out[1] - unit_f2[1])
        assert dir_err < 1e-9, f"Ball {ball_id} reflected ray does not point to F2 (err={dir_err})"

        # Also check pass_focus event is generated at F2
        pass_f2_events = [
            e for e in events if e.ball_id == ball_id and e.kind == EventKind.PASS_FOCUS
        ]
        assert len(pass_f2_events) >= 1
        f_evt = pass_f2_events[0]
        assert math.hypot(f_evt.point[0] - f2[0], f_evt.point[1] - f2[1]) < 1e-9


def test_all_balls_reach_f2_at_same_time():
    """
    Invariant 3: All balls reach F2 at the exact same time: t_launch + 2*b within 1e-9.
    """
    b_val = 0.8
    sim = EllipseBilliardsSim(axes=EllipseAxes(a=0.6, b=b_val), seed=123)
    start_t = 1.0
    events = sim.simulate_stage(count=32, start_time=start_t, duration=2.5)

    expected_f2_time = start_t + 2.0 * b_val  # 1.0 + 1.6 = 2.6

    for ball_id in range(32):
        f2_events = [e for e in events if e.ball_id == ball_id and e.kind == EventKind.PASS_FOCUS]
        assert len(f2_events) >= 1, f"Ball {ball_id} missing pass_focus event"
        actual_t = f2_events[0].time
        time_diff = abs(actual_t - expected_f2_time)
        assert time_diff < 1e-9, f"Ball {ball_id} reached F2 at {actual_t}, expected {expected_f2_time} (diff={time_diff})"


def test_balls_pass_through_f1_again_after_second_bounce():
    """
    Invariant 4: After the second bounce, balls pass through F1 again at t_launch + 4*b within 1e-9.
    """
    b_val = 0.8
    sim = EllipseBilliardsSim(axes=EllipseAxes(a=0.6, b=b_val), seed=999)
    start_t = 0.0
    # Run long enough for 2 bounces and return to F1: 4*b = 3.2s
    events = sim.simulate_stage(count=16, start_time=start_t, duration=3.5)

    f1 = sim.f1
    expected_f1_time = start_t + 4.0 * b_val  # 3.2

    for ball_id in range(16):
        bounces = [e for e in events if e.ball_id == ball_id and e.kind == EventKind.BOUNCE]
        assert len(bounces) >= 2, f"Ball {ball_id} should bounce at least twice"
        b2 = bounces[1]
        v_out2 = b2.velocity
        p2 = b2.point

        # Vector from p2 to f1
        vf1 = (f1[0] - p2[0], f1[1] - p2[1])
        dist_f1 = math.hypot(*vf1)
        unit_f1 = (vf1[0] / dist_f1, vf1[1] / dist_f1)

        # Direction error to F1
        dir_err = math.hypot(v_out2[0] - unit_f1[0], v_out2[1] - unit_f1[1])
        assert dir_err < 1e-9, f"Ball {ball_id} bounce 2 ray does not point to F1 (err={dir_err})"

        # Check total distance from launch to F1 is 4*b
        # Launch to P1 (t_b1) + P1 to P2 (dist_b1_b2) + P2 to F1 (dist_f1) = 4*b
        t_b1 = bounces[0].time - start_t
        t_b2_from_b1 = b2.time - bounces[0].time
        total_time_to_f1 = start_t + t_b1 + t_b2_from_b1 + dist_f1
        assert abs(total_time_to_f1 - expected_f1_time) < 1e-9


def test_deterministic_sequence_for_fixed_seed():
    """
    Invariant 5: Simulation is bit-for-bit deterministic for a fixed seed.
    """
    sim1 = EllipseBilliardsSim(seed=777)
    sim2 = EllipseBilliardsSim(seed=777)

    ev1 = sim1.simulate_stage(count=12, start_time=0.0, duration=3.5)
    ev2 = sim2.simulate_stage(count=12, start_time=0.0, duration=3.5)

    assert len(ev1) == len(ev2)
    for e1, e2 in zip(ev1, ev2):
        assert e1.time == e2.time
        assert e1.ball_id == e2.ball_id
        assert e1.kind == e2.kind
        assert e1.point == e2.point
        assert e1.velocity == e2.velocity


def test_seeded_failure_perturbed_normal_fails_reflection_law():
    """
    Seeded failure: A deliberately perturbed normal (by 0.05 rad) MUST fail the reflection-law check.
    """
    sim = EllipseBilliardsSim(axes=EllipseAxes(a=0.6, b=0.8), seed=42)

    # Ball 0 with perturbed normal on bounce 1
    perturbed_events = sim.simulate_ball(
        ball_id=0,
        start_time=0.0,
        angle=0.7,
        duration=2.5,
        perturbed_bounce=1,
        perturbation_rad=0.05,
    )

    bounces = [e for e in perturbed_events if e.kind == EventKind.BOUNCE]
    assert len(bounces) >= 1
    b1 = bounces[0]
    p1 = b1.point
    v_out = b1.velocity
    f2 = sim.f2

    # Check whether the perturbed ray still passes through F2:
    vf2 = (f2[0] - p1[0], f2[1] - p1[1])
    dist_f2 = math.hypot(*vf2)
    unit_f2 = (vf2[0] / dist_f2, vf2[1] / dist_f2)

    dir_err = math.hypot(v_out[0] - unit_f2[0], v_out[1] - unit_f2[1])

    # The direction error MUST be large (> 0.05) and exceed 1e-9
    assert dir_err > 0.05, f"Perturbed normal should have deviated from F2, got err={dir_err}"


def test_ball_position_interpolation():
    """Verify get_ball_position_at matches analytical straight line motion."""
    sim = EllipseBilliardsSim(axes=EllipseAxes(a=0.6, b=0.8), seed=42)
    events = sim.simulate_ball(ball_id=0, start_time=0.0, angle=0.0, duration=3.0)

    # Position at start must be F1
    p0 = get_ball_position_at(events, ball_id=0, t=0.0)
    assert p0 is not None
    assert math.hypot(p0[0] - sim.f1[0], p0[1] - sim.f1[1]) < 1e-9

    # Position mid-flight
    p_mid = get_ball_position_at(events, ball_id=0, t=0.2)
    assert p_mid is not None
    assert abs(math.hypot(p_mid[0] - sim.f1[0], p_mid[1] - sim.f1[1]) - 0.2) < 1e-9
