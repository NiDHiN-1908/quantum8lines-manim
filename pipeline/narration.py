"""
Narration audio builder with pause handling, checkpointing, and timing generation.
Follows SPEC.md Sections 5.2, 8, 10 and Milestone M3a Step 3.
"""

from pathlib import Path
import json
import hashlib
from typing import Dict, Any, Union, Optional, List
import numpy as np
import soundfile as sf

from pipeline.tts.schemas import VoiceProfile, load_voice_profile
from pipeline.tts.base import TTSEngine
from pipeline.tts import get_tts_engine
from pipeline.lexicon import prepare_text


def compute_line_hash(
    prepared_text: str,
    engine_name: str,
    voice_name: str,
    speed: float,
) -> str:
    """Computes a deterministic hash for a line's synthesis parameters."""
    key = f"{prepared_text}::{engine_name}::{voice_name}::{speed:.3f}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_narration(
    chapter_dir: Union[str, Path],
    profile_id: Union[str, VoiceProfile],
    engine: Optional[TTSEngine] = None,
) -> Dict[str, Any]:
    """
    Builds chapter narration audio from script.json:
    1. Reads script.json (SPEC Section 5.2).
    2. Synthesizes each line with phonetic respelling applied (prepare_text).
    3. Writes audio/lines/<id>.wav for each line.
    4. Applies checkpointing: skips lines whose input hash is unchanged.
    5. Appends configured pause_ms after each line (aha pause if beat=='aha', sentence pause otherwise).
    6. Concatenates all lines into audio/narration.wav.
    7. Emits audio/timings.json with absolute start/end per line in seconds.

    Arguments:
        chapter_dir: Path to chapter directory containing script.json.
        profile_id: VoiceProfile instance or profile ID string (e.g. 'calm_curious_heart').
        engine: Optional TTSEngine override (useful for testing with mock engines).

    Returns:
        Dictionary containing timings metadata and lines.
    """
    chapter_path = Path(chapter_dir)
    script_path = chapter_path / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(f"script.json not found in {chapter_path}")

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    # Resolve Voice Profile
    if isinstance(profile_id, VoiceProfile):
        profile = profile_id
    else:
        profile = load_voice_profile(profile_id)

    # Resolve Engine
    if engine is None:
        engine = get_tts_engine(profile.engine)

    # Setup directories
    audio_dir = chapter_path / "audio"
    lines_dir = audio_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    # Load checkpoint cache
    checkpoint_path = audio_dir / ".checkpoint.json"
    checkpoints: Dict[str, str] = {}
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoints = json.load(f)
        except Exception:
            checkpoints = {}

    lines = script_data.get("lines", [])
    line_timings: List[Dict[str, Any]] = []
    audio_chunks: List[np.ndarray] = []
    sample_rate: Optional[int] = None
    current_time_sec: float = 0.0

    for line in lines:
        line_id = str(line.get("id"))
        raw_text = str(line.get("text", ""))
        beat = str(line.get("beat", "")).lower()

        # Phonetic preparation (captions retain raw_text)
        prepared_text = prepare_text(line, lexicon=profile.lexicon)

        # Checkpointing
        line_hash = compute_line_hash(
            prepared_text=prepared_text,
            engine_name=engine.name,
            voice_name=profile.voice,
            speed=profile.speed,
        )

        wav_path = lines_dir / f"{line_id}.wav"
        can_reuse = (
            line_id in checkpoints
            and checkpoints[line_id] == line_hash
            and wav_path.exists()
        )

        if can_reuse:
            # Read existing cached wav
            samples, sr = sf.read(str(wav_path), dtype="float32")
            if samples.ndim > 1:
                samples = samples[:, 0]
            if sample_rate is None:
                sample_rate = sr
        else:
            # Synthesize through engine
            samples, sr = engine.synthesize(prepared_text, profile)
            if samples.ndim > 1:
                samples = samples[:, 0]
            samples = np.asarray(samples, dtype=np.float32)
            if sample_rate is None:
                sample_rate = sr

            # Write line wav
            sf.write(str(wav_path), samples, sr)
            checkpoints[line_id] = line_hash

        # Pause duration calculation
        if beat == "aha":
            pause_sec = profile.get_aha_pause_sec()
        else:
            pause_sec = profile.get_sentence_pause_sec()

        line_duration_sec = len(samples) / float(sample_rate)
        start_sec = current_time_sec
        end_sec = start_sec + line_duration_sec

        # Generate silence samples for the pause
        num_pause_samples = int(round(pause_sec * sample_rate))
        pause_samples = np.zeros(num_pause_samples, dtype=np.float32)

        # Record timing metadata
        line_timings.append({
            "id": line_id,
            "beat": beat,
            "text": raw_text,
            "prepared_text": prepared_text,
            "start": round(start_sec, 4),
            "end": round(end_sec, 4),
            "duration": round(line_duration_sec, 4),
            "pause_after": round(pause_sec, 4),
        })

        # Append audio and silence to narration buffer
        audio_chunks.append(samples)
        if num_pause_samples > 0:
            audio_chunks.append(pause_samples)

        current_time_sec = end_sec + (num_pause_samples / float(sample_rate))

    # Assemble concatenated narration.wav
    if audio_chunks and sample_rate:
        narration_samples = np.concatenate(audio_chunks, dtype=np.float32)
    else:
        narration_samples = np.array([], dtype=np.float32)
        sample_rate = sample_rate or 24000

    narration_path = audio_dir / "narration.wav"
    sf.write(str(narration_path), narration_samples, sample_rate)

    # Save timings.json
    total_duration_sec = len(narration_samples) / float(sample_rate)
    timings_data = {
        "chapter": script_data.get("chapter", chapter_path.name),
        "profile_id": profile.id,
        "sample_rate": sample_rate,
        "total_duration": round(total_duration_sec, 4),
        "lines": line_timings,
    }

    timings_path = audio_dir / "timings.json"
    with open(timings_path, "w", encoding="utf-8") as f:
        json.dump(timings_data, f, indent=2)

    # Save updated checkpoints
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoints, f, indent=2)

    return timings_data
