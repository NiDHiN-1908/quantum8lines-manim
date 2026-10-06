"""
Pydantic schemas for voice profiles and TTS configuration.
Follows SPEC.md Section 10 and Milestone M3a.
"""

from pathlib import Path
from typing import Dict, Literal, Optional, Union
from pydantic import BaseModel, Field


class PauseMs(BaseModel):
    """Pause durations in milliseconds after sentences and payoff lines."""
    sentence: int = Field(default=300, description="Pause duration in ms after standard lines")
    aha: int = Field(default=600, description="Pause duration in ms after 'aha' payoff lines")


VoiceStatus = Literal["candidate", "approved", "retired"]


class VoiceProfile(BaseModel):
    """
    Voice profile specification for Quantum8Lines narration synthesis.
    Profiles are stored in brand/voices/<id>.json.
    """
    id: str = Field(description="Unique profile identifier, e.g. calm_curious_heart")
    engine: str = Field(default="kokoro", description="TTS engine name (e.g. kokoro)")
    voice: str = Field(description="Voice identifier in the engine's internal catalog")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speaking rate multiplier")
    tone: str = Field(description="Tone preset: calm_curious | energetic_playful | serious_cinematic")
    pause_ms: Dict[str, int] = Field(
        default_factory=lambda: {"sentence": 300, "aha": 600},
        description="Pause durations in milliseconds"
    )
    lexicon: str = Field(default="brand/lexicon.json", description="Path to pronunciation lexicon JSON")
    postfx: str = Field(default="warm_narration", description="Post-processing FX profile identifier")
    license_note: str = Field(description="Verification of the model's commercial license")
    status: VoiceStatus = Field(default="candidate", description="candidate | approved | retired")

    def get_sentence_pause_sec(self) -> float:
        """Returns the standard sentence pause duration in seconds."""
        return self.pause_ms.get("sentence", 300) / 1000.0

    def get_aha_pause_sec(self) -> float:
        """Returns the 'aha' pause duration in seconds."""
        return self.pause_ms.get("aha", 600) / 1000.0


def load_voice_profile(path_or_id: Union[str, Path]) -> VoiceProfile:
    """
    Loads a VoiceProfile from a file path or resolves from brand/voices/<id>.json.
    """
    p = Path(path_or_id)
    if not p.exists() and not str(p).endswith(".json"):
        p = Path("brand") / "voices" / f"{path_or_id}.json"

    if not p.exists():
        raise FileNotFoundError(f"Voice profile file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        import json
        data = json.load(f)

    return VoiceProfile.model_validate(data)
