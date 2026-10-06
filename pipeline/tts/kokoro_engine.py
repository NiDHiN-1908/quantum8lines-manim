"""
Kokoro-82M ONNX TTS engine adapter.
Follows SPEC.md Section 10 and Milestone M3a Step 1.
"""

from pathlib import Path
from typing import Tuple, List, Optional, Union
import numpy as np

from pipeline.tts.base import TTSEngine
from pipeline.tts.schemas import VoiceProfile

DEFAULT_MODEL_PATH = Path("models/kokoro-v1.0.int8.onnx")
DEFAULT_VOICES_PATH = Path("models/voices-v1.0.bin")


class KokoroEngine(TTSEngine):
    """
    Adapter for Kokoro-82M ONNX text-to-speech synthesis.
    Discovers voices dynamically from the official binary voices catalog.
    """

    def __init__(
        self,
        model_path: Union[str, Path] = DEFAULT_MODEL_PATH,
        voices_path: Union[str, Path] = DEFAULT_VOICES_PATH,
    ):
        self.model_path = Path(model_path)
        self.voices_path = Path(voices_path)
        self._kokoro = None

    @property
    def name(self) -> str:
        return "kokoro"

    @property
    def is_available(self) -> bool:
        return self.model_path.exists() and self.voices_path.exists()

    def _ensure_loaded(self):
        if not self.is_available:
            raise FileNotFoundError(
                f"Kokoro model files not found: "
                f"model='{self.model_path}' (exists={self.model_path.exists()}), "
                f"voices='{self.voices_path}' (exists={self.voices_path.exists()})."
            )
        if self._kokoro is None:
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))

    def get_voices(self) -> List[str]:
        """Discover available voice names from the loaded voices catalog."""
        self._ensure_loaded()
        return self._kokoro.get_voices()

    def synthesize(self, text: str, profile: VoiceProfile) -> Tuple[np.ndarray, int]:
        """Synthesize text using the Kokoro model and specified voice profile."""
        self._ensure_loaded()

        available = self.get_voices()
        if profile.voice not in available:
            raise ValueError(
                f"Voice '{profile.voice}' not found in Kokoro catalog. "
                f"Available voices ({len(available)}): {available[:10]}..."
            )

        samples, sample_rate = self._kokoro.create(
            text=text,
            voice=profile.voice,
            speed=float(profile.speed),
        )

        return np.asarray(samples, dtype=np.float32), int(sample_rate)
