import os
import json
from faster_whisper import WhisperModel

class WhisperSync:
    def __init__(self, model_size: str = "tiny", device: str = "cpu"):
        """
        Initialize the Whisper model.
        device can be "cpu" or "cuda" (if GPU is available).
        """
        print(f"Initializing Whisper model ({model_size}) on {device}...")
        self.model = WhisperModel(model_size, device=device, compute_type="int8")

    def align(self, audio_path: str, output_json_path: str = None) -> dict:
        """
        Transcribe the audio and extract word-level timestamps.
        Saves the output to output_json_path if provided.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"Aligning audio: {audio_path}")
        segments, info = self.model.transcribe(audio_path, word_timestamps=True)

        word_alignments = []
        for segment in segments:
            if segment.words:
                for word_info in segment.words:
                    # Clean up the word text (strip leading/trailing space)
                    cleaned_word = word_info.word.strip()
                    word_alignments.append({
                        "word": cleaned_word,
                        "start": round(word_info.start, 3),
                        "end": round(word_info.end, 3)
                    })

        result = {"words": word_alignments}

        if output_json_path:
            os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Word timestamps saved to {output_json_path}")

        return result

if __name__ == "__main__":
    # Test execution
    test_audio = "test_output/test_eigen.wav"
    if os.path.exists(test_audio):
        sync = WhisperSync(device="cpu")
        alignments = sync.align(test_audio, "test_output/test_timestamps.json")
        print("Test alignment complete. Words found:")
        for w in alignments["words"][:10]:
            print(f"  {w['word']}: {w['start']}s -> {w['end']}s")
    else:
        print(f"Please run tts_engine.py first to generate {test_audio}")
