"""
Audition set renderer for voice candidate profiles.
Follows SPEC.md Section 10 and Milestone M3a Step 4.
Renders brand/voices/audition_set.json for all candidate profiles into
build/voice_audition/<profile_id>/ and outputs build/voice_audition/manifest.json.
"""

from pathlib import Path
import json
import time
from typing import Dict, Any, List

from pipeline.tts.schemas import VoiceProfile, load_voice_profile
from pipeline.tts import get_tts_engine
from pipeline.narration import build_narration


DEFAULT_AUDITION_SET_PATH = Path("brand/voices/audition_set.json")
DEFAULT_VOICES_DIR = Path("brand/voices")
DEFAULT_BUILD_DIR = Path("build/voice_audition")


def get_candidate_profiles(voices_dir: Path = DEFAULT_VOICES_DIR) -> List[VoiceProfile]:
    """Finds and loads all voice profiles with status == 'candidate'."""
    candidates = []
    for file_path in sorted(voices_dir.glob("*.json")):
        if file_path.name in ["audition_set.json", "scores.json"]:
            continue
        try:
            profile = load_voice_profile(file_path)
            if profile.status == "candidate":
                candidates.append(profile)
        except Exception:
            continue
    return candidates


def render_audition_set(
    audition_set_path: Path = DEFAULT_AUDITION_SET_PATH,
    voices_dir: Path = DEFAULT_VOICES_DIR,
    build_dir: Path = DEFAULT_BUILD_DIR,
) -> Dict[str, Any]:
    """
    Renders the fixed audition set for every candidate voice profile.
    Produces build/voice_audition/<profile_id>/ and build/voice_audition/manifest.json.
    Reports render timings per profile.
    """
    if not audition_set_path.exists():
        raise FileNotFoundError(f"Audition set file not found: {audition_set_path}")

    with open(audition_set_path, "r", encoding="utf-8") as f:
        audition_data = json.load(f)

    candidates = get_candidate_profiles(voices_dir)
    if not candidates:
        raise RuntimeError(f"No candidate voice profiles found in {voices_dir}")

    build_dir.mkdir(parents=True, exist_ok=True)
    engine = get_tts_engine("kokoro")
    if not engine.is_available:
        raise RuntimeError("Kokoro TTS model files not available in models/")

    manifest_entries: List[Dict[str, Any]] = []
    print(f"\n=======================================================")
    print(f"Rendering Voice Audition Set for {len(candidates)} Candidate Profiles")
    print(f"=======================================================\n")

    for profile in candidates:
        profile_dir = build_dir / profile.id
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Write chapter script.json for narration builder
        script_path = profile_dir / "script.json"
        chapter_script = {
            "chapter": f"audition_{profile.id}",
            "lines": audition_data.get("lines", []),
        }
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(chapter_script, f, indent=2)

        # Synthesize and time
        t_start = time.perf_counter()
        timings = build_narration(profile_dir, profile, engine=engine)
        render_time = time.perf_counter() - t_start

        entry = {
            "profile_id": profile.id,
            "voice": profile.voice,
            "speed": profile.speed,
            "tone": profile.tone,
            "render_time_sec": round(render_time, 3),
            "total_audio_duration_sec": timings["total_duration"],
            "lines_count": len(timings["lines"]),
            "narration_wav": str(profile_dir / "audio" / "narration.wav"),
            "timings_json": str(profile_dir / "audio" / "timings.json"),
        }
        manifest_entries.append(entry)

        print(
            f"  [+] {profile.id:<28} | Voice: {profile.voice:<10} | "
            f"Speed: {profile.speed:<4.2f} | Audio: {timings['total_duration']:<6.2f}s | "
            f"Render: {render_time:<6.2f}s"
        )

    manifest_data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profiles_count": len(candidates),
        "profiles": manifest_entries,
    }

    manifest_path = build_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(f"\nManifest written to: {manifest_path}")
    return manifest_data


if __name__ == "__main__":
    render_audition_set()
