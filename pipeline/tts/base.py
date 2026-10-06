"""
Base abstract class for TTS engines.
Follows SPEC.md Section 10:
Engine abstraction: pipeline/tts exposes one interface. Adding or replacing
an engine never touches scenes, scripts, or captions.
"""

from abc import ABC, abstractmethod
from typing import Tuple, List
import numpy as np

from pipeline.tts.schemas import VoiceProfile


class TTSEngine(ABC):
    """Abstract interface for text-to-speech synthesis engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the engine (e.g. 'kokoro')."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the engine's model weights and binaries are available."""
        pass

    @abstractmethod
    def get_voices(self) -> List[str]:
        """Discovers and returns list of voice names directly from the engine catalog."""
        pass

    @abstractmethod
    def synthesize(self, text: str, profile: VoiceProfile) -> Tuple[np.ndarray, int]:
        """
        Synthesizes text into audio samples according to voice profile settings.
        Returns:
            samples: 1D float32 numpy array representing normalized audio samples.
            sample_rate: Audio sampling rate in Hz (e.g. 24000).
        """
        pass
