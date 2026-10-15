"""
Musical scale definitions, root frequency parsing, and deterministic pitch mapping.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

import math
import re
from typing import Any, Dict, List, Tuple, Union


# Musical scale intervals in semitones above the root
SCALES: Dict[str, List[int]] = {
    "pentatonic_major": [0, 2, 4, 7, 9],
    "major": [0, 2, 4, 5, 7, 9, 11],
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "whole_tone": [0, 2, 4, 6, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
}

# Alias for whole-tone with hyphen
SCALES["whole-tone"] = SCALES["whole_tone"]

NOTE_SEMITONES: Dict[str, int] = {
    "C": 0, "B#": 0,
    "C#": 1, "DB": 1,
    "D": 2,
    "D#": 3, "EB": 3,
    "E": 4, "FB": 4,
    "F": 5, "E#": 5,
    "F#": 6, "GB": 6,
    "G": 7,
    "G#": 8, "AB": 8,
    "A": 9,
    "A#": 10, "BB": 10,
    "B": 11, "CB": 11,
}


def parse_root_hz(root: Union[str, float]) -> float:
    """
    Parses a root note string (e.g. 'C4', 'A3', 'F#4') or direct float frequency into Hz.
    Standard A4 = 440.0 Hz equal-temperament tuning.
    """
    if isinstance(root, (int, float)):
        if root <= 0:
            raise ValueError(f"Root frequency must be positive, got {root}")
        return float(root)

    s = str(root).strip().upper()
    # Match Note name (letter + optional #/b) and Octave integer
    m = re.match(r"^([A-G][#B]?)(-?\d+)$", s)
    if not m:
        # Fallback to direct float parse if string is numeric e.g. "261.63"
        try:
            val = float(s)
            if val <= 0:
                raise ValueError
            return val
        except ValueError:
            raise ValueError(f"Invalid root note format: '{root}'. Expected note like 'C4' or float Hz.")

    note_name, octave_str = m.group(1), m.group(2)
    if note_name not in NOTE_SEMITONES:
        raise ValueError(f"Unknown note name '{note_name}' in root '{root}'")

    semitone = NOTE_SEMITONES[note_name]
    octave = int(octave_str)
    # MIDI note number: C4 = 60, A4 = 69
    midi = (octave + 1) * 12 + semitone
    freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
    return float(freq)


def get_note_frequency(
    index: int,
    root_hz: float,
    scale_name: str = "pentatonic_major",
    octaves: int = 3,
) -> float:
    """
    Computes equal-temperament frequency for an index within a scale and octave span.
    Strictly follows 12-TET equal-temperament ratios: f = root_hz * 2^(semitones / 12).
    """
    if scale_name not in SCALES:
        raise ValueError(f"Unknown scale '{scale_name}'. Supported: {list(SCALES.keys())}")

    scale = SCALES[scale_name]
    scale_len = len(scale)
    if scale_len == 0:
        return root_hz

    octave_offset = (index // scale_len) % max(1, octaves)
    degree_idx = index % scale_len
    semitone = octave_offset * 12 + scale[degree_idx]

    return root_hz * (2.0 ** (semitone / 12.0))


def event_to_pitch(
    event: Any,
    root_hz: float,
    scale_name: str = "pentatonic_major",
    octaves: int = 3,
    mapping_mode: str = "ball_id",
) -> float:
    """
    Deterministically computes note pitch from a simulation event (ball_id or height).
    Never uses random numbers.
    """
    if mapping_mode == "height" and hasattr(event, "point") and event.point is not None:
        y = float(event.point[1])
        # Normalize assuming nominal bounds [-0.8, 0.8]
        norm = max(0.0, min(1.0, (y + 0.8) / 1.6))
        scale = SCALES.get(scale_name, SCALES["pentatonic_major"])
        total_notes = len(scale) * max(1, octaves)
        index = int(round(norm * (total_notes - 1)))
    else:
        index = int(getattr(event, "ball_id", 0))

    return get_note_frequency(index, root_hz, scale_name, octaves)
