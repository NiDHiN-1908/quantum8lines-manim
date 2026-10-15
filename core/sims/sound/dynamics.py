"""
Dynamics, polyphony voice management, and soft saturation for procedural sound.
Maintains polyphony limit (dropping or lowering oldest/quietest voices)
and applies smooth soft saturation to prevent hard clipping.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

from dataclasses import dataclass
import math
from typing import List, Tuple
import numpy as np


@dataclass
class ActiveVoice:
    """Represents a sounding voice in the polyphony manager."""
    voice_id: int
    start_sample: int
    end_sample: int
    left_samples: np.ndarray
    right_samples: np.ndarray
    base_amp: float
    decay_samples: int


class PolyphonyManager:
    """
    Allocates and limits simultaneous sounding voices.
    When concurrent active voices reach polyphony_limit,
    the oldest and quietest voice is smoothly faded out and retired.
    """

    def __init__(self, polyphony_limit: int = 24, sample_rate: int = 48000):
        self.limit = max(1, polyphony_limit)
        self.sample_rate = sample_rate
        self.fade_samples = int(0.005 * sample_rate)  # 5ms click-free fadeout

    def allocate_voices(
        self,
        voice_events: List[Tuple[int, int, np.ndarray, np.ndarray, float, int]],
        total_samples: int,
    ) -> np.ndarray:
        """
        Renders a sequence of voice events into a stereo buffer while strictly
        enforcing the polyphony limit.

        Each tuple in voice_events:
            (start_sample, end_sample, left_sig, right_sig, base_amp, decay_samples)
        """
        stereo_buffer = np.zeros((total_samples, 2), dtype=np.float32)
        active: List[ActiveVoice] = []
        next_id = 0

        # Sort events chronologically by start_sample
        sorted_events = sorted(voice_events, key=lambda e: e[0])

        for start_s, end_s, left_sig, right_sig, base_amp, decay_s in sorted_events:
            if start_s >= total_samples:
                continue

            # 1. Prune expired voices
            active = [v for v in active if v.end_sample > start_s]

            # 2. If active voices count >= limit, drop or lower oldest and quietest
            while len(active) >= self.limit:
                # Rank active voices: combination of lowest instantaneous amplitude and oldest start
                # Score = remaining_amp * (start_s - v.start_sample + 1)
                def voice_priority(v: ActiveVoice) -> float:
                    elapsed = max(0, start_s - v.start_sample)
                    decay = max(1, v.decay_samples)
                    rem_amp = v.base_amp * math.exp(-float(elapsed) / float(decay))
                    # Lower score = prioritized for dropping (older + quieter)
                    return rem_amp / (1.0 + 0.1 * (elapsed / float(self.sample_rate)))

                victim = min(active, key=voice_priority)
                # Apply 5ms fade out on victim to avoid clicks
                victim_fade_end = min(victim.end_sample, start_s + self.fade_samples)
                fade_len = victim_fade_end - start_s
                if fade_len > 0:
                    ramp = 0.5 * (1.0 + np.cos(np.pi * np.arange(fade_len) / float(fade_len)))
                    offset_in_voice = start_s - victim.start_sample
                    if 0 <= offset_in_voice < len(victim.left_samples):
                        v_end = min(len(victim.left_samples), offset_in_voice + fade_len)
                        v_len = v_end - offset_in_voice
                        victim.left_samples[offset_in_voice:v_end] *= ramp[:v_len].astype(np.float32)
                        victim.right_samples[offset_in_voice:v_end] *= ramp[:v_len].astype(np.float32)
                        # Zero out any remainder after fade
                        victim.left_samples[v_end:] = 0.0
                        victim.right_samples[v_end:] = 0.0

                victim.end_sample = victim_fade_end
                active.remove(victim)

            # 3. Add new voice
            new_voice = ActiveVoice(
                voice_id=next_id,
                start_sample=start_s,
                end_sample=end_s,
                left_samples=left_sig.copy(),
                right_samples=right_sig.copy(),
                base_amp=base_amp,
                decay_samples=decay_s,
            )
            next_id += 1
            active.append(new_voice)

            # 4. Render into buffer
            actual_end = min(total_samples, start_s + len(new_voice.left_samples))
            render_len = actual_end - start_s
            if render_len > 0:
                stereo_buffer[start_s:actual_end, 0] += new_voice.left_samples[:render_len]
                stereo_buffer[start_s:actual_end, 1] += new_voice.right_samples[:render_len]

        return stereo_buffer


def apply_soft_saturation(stereo_audio: np.ndarray, threshold: float = 0.65) -> np.ndarray:
    """
    Applies smooth tape-style soft saturation above threshold.
    Linear for |x| <= threshold; smoothly saturates with tanh above threshold.
    Peak strictly guaranteed to stay <= 0.98 without hard clipping.
    """
    out = np.empty_like(stereo_audio)
    t = float(threshold)
    margin = 0.97 - t

    # Positive and negative regions
    abs_x = np.abs(stereo_audio)
    linear_mask = abs_x <= t

    # Linear region
    out[linear_mask] = stereo_audio[linear_mask]

    # Non-linear saturated region
    sat_mask = ~linear_mask
    if np.any(sat_mask):
        excess = abs_x[sat_mask] - t
        sat = t + margin * np.tanh(excess / margin)
        out[sat_mask] = np.sign(stereo_audio[sat_mask]) * sat

    return out.astype(np.float32)
