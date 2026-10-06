"""
TTS Engine abstraction and adapters package.
Follows SPEC.md Section 10.
"""

from typing import Dict, Type
from pipeline.tts.base import TTSEngine
from pipeline.tts.schemas import VoiceProfile, load_voice_profile
from pipeline.tts.kokoro_engine import KokoroEngine

ENGINES: Dict[str, Type[TTSEngine]] = {
    "kokoro": KokoroEngine,
}


def get_tts_engine(name: str = "kokoro", **kwargs) -> TTSEngine:
    """Factory helper to obtain a configured TTSEngine instance."""
    engine_cls = ENGINES.get(name.lower())
    if not engine_cls:
        raise ValueError(f"Unknown TTS engine '{name}'. Available engines: {list(ENGINES.keys())}")
    return engine_cls(**kwargs)


__all__ = [
    "TTSEngine",
    "KokoroEngine",
    "VoiceProfile",
    "load_voice_profile",
    "get_tts_engine",
]
