"""
Rhythm grid quantization for procedural simulation sound.
Quantizes event times to a musical tempo grid with a strict 30ms maximum shift
so audio remains tightly synchronized with visual physics.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

import math
from typing import Any, List, Optional


MAX_QUANTIZE_SHIFT_SEC = 0.030  # Strict 30ms limit


def quantize_event_time(
    t: float,
    tempo: float = 120.0,
    subdivision: int = 4,
    max_shift_sec: float = MAX_QUANTIZE_SHIFT_SEC,
) -> float:
    """
    Snaps an event timestamp to the nearest grid line defined by tempo (BPM) and subdivision.
    Enforces a strict upper bound of max_shift_sec (30 ms) so sound never visibly desyncs from picture.
    """
    if tempo <= 0.0 or subdivision <= 0:
        return t

    # Duration of one subdivision interval in seconds
    grid_interval = 60.0 / (float(tempo) * float(subdivision))
    if grid_interval <= 1e-6:
        return t

    # Nearest grid timestamp
    grid_index = round(t / grid_interval)
    t_target = grid_index * grid_interval

    # Calculate shift
    delta = t_target - t

    # Clamp shift to [-max_shift_sec, max_shift_sec]
    clamped_delta = max(-max_shift_sec, min(max_shift_sec, delta))
    t_quantized = max(0.0, t + clamped_delta)

    return t_quantized


def quantize_events(
    events: List[Any],
    enabled: bool = False,
    tempo: float = 120.0,
    subdivision: int = 4,
    max_shift_sec: float = MAX_QUANTIZE_SHIFT_SEC,
) -> List[Any]:
    """
    Optionally quantizes a list of simulation events.
    If enabled is False, returns the events unchanged.
    If enabled is True, returns new events with time shifted by at most max_shift_sec.
    """
    if not enabled:
        return events

    quantized_list = []
    for evt in events:
        # Create a copy or updated event if pydantic / dataclass
        new_t = quantize_event_time(
            evt.time,
            tempo=tempo,
            subdivision=subdivision,
            max_shift_sec=max_shift_sec,
        )
        if hasattr(evt, "model_copy"):
            evt_copy = evt.model_copy(update={"time": new_t})
        elif hasattr(evt, "copy"):
            evt_copy = evt.copy(update={"time": new_t})
        else:
            # Dataclass or generic object
            import copy
            evt_copy = copy.copy(evt)
            evt_copy.time = new_t

        quantized_list.append(evt_copy)

    return quantized_list
