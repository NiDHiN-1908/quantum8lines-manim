"""
Spatialization and acoustic environment: constant-power stereo panning
and Schroeder-style algorithmic reverberator in pure NumPy/SciPy.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

import math
from typing import Tuple
import numpy as np
import scipy.signal


def compute_stereo_gains(x: float, a: float) -> Tuple[float, float]:
    """
    Computes constant-power stereo panning (left_gain, right_gain) from x position in [-a, a].
    Total energy left^2 + right^2 == 1.0.
    """
    p = max(-1.0, min(1.0, x / max(1e-6, a)))
    theta = (math.pi / 4.0) * (p + 1.0)  # in [0, pi/2]
    left = math.cos(theta)
    right = math.sin(theta)
    return (left, right)


def _schroeder_reverb_channel(
    signal: np.ndarray,
    comb_delays: Tuple[int, int, int, int],
    allpass_delays: Tuple[int, int],
    sample_rate: int,
    decay_sec: float,
) -> np.ndarray:
    """Processes a single audio channel through Schroeder parallel combs and series allpasses."""
    t60 = max(0.2, min(decay_sec, 6.0))
    sr = float(sample_rate)

    comb_outputs = []
    for d in comb_delays:
        # Feedback gain derived from T60 reverberation decay time: g = 10^(-3 * d / (T60 * sr))
        g = float(10.0 ** (-3.0 * float(d) / (t60 * sr)))
        g = max(0.1, min(0.92, g))

        a = np.zeros(d + 1, dtype=np.float64)
        a[0] = 1.0
        a[d] = -g
        b = np.array([1.0], dtype=np.float64)

        y_comb = scipy.signal.lfilter(b, a, signal.astype(np.float64))
        comb_outputs.append(y_comb)

    comb_mix = (sum(comb_outputs) / float(len(comb_outputs))).astype(np.float64)

    # Series allpass diffusion stages
    ga = 0.70
    current = comb_mix
    for da in allpass_delays:
        b_ap = np.zeros(da + 1, dtype=np.float64)
        b_ap[0] = -ga
        b_ap[da] = 1.0

        a_ap = np.zeros(da + 1, dtype=np.float64)
        a_ap[0] = 1.0
        a_ap[da] = -ga

        current = scipy.signal.lfilter(b_ap, a_ap, current)

    return current.astype(np.float32)


def apply_schroeder_reverb(
    stereo_audio: np.ndarray,
    sample_rate: int = 48000,
    wet_level: float = 0.15,
    decay_sec: float = 1.2,
) -> np.ndarray:
    """
    Applies a stereo Schroeder algorithmic reverberator.
    Uses 4 parallel feedback comb filters and 2 series allpass filters per channel,
    with prime-offset delays between channels for stereo decorrelation.
    """
    wet = max(0.0, min(1.0, float(wet_level)))
    if wet <= 1e-4:
        return stereo_audio

    # Mutually prime delay lengths in samples (~28 to 44 ms)
    # Left channel comb and allpass delays
    combs_l = (1427, 1619, 1823, 2087)
    allpass_l = (227, 79)

    # Right channel slightly offset for lush stereo decorrelation
    combs_r = (1453, 1597, 1847, 2111)
    allpass_r = (241, 83)

    left_in = stereo_audio[:, 0]
    right_in = stereo_audio[:, 1]

    rev_l = _schroeder_reverb_channel(left_in, combs_l, allpass_l, sample_rate, decay_sec)
    rev_r = _schroeder_reverb_channel(right_in, combs_r, allpass_r, sample_rate, decay_sec)

    dry = 1.0 - wet
    out_left = dry * left_in + wet * rev_l
    out_right = dry * right_in + wet * rev_r

    return np.column_stack([out_left, out_right]).astype(np.float32)
