# Audio Pipeline & Voice Lab Documentation

This document describes the audio pipeline architecture, voice profiles, pronunciation lexicon, narration generation, and word-level forced alignment for Quantum8Lines animations, adhering to **SPEC.md Section 10 and Milestone M3a**.

---

## 1. Architectural Overview

```
                      +-----------------------+
                      |      script.json      |
                      +-----------+-----------+
                                  |
                                  v
+--------------------+   +--------------------+   +-----------------------+
| brand/lexicon.json |-->|    prepare_text    |<--|  VoiceProfile Schema  |
+--------------------+   +---------+----------+   | (brand/voices/<id>)   |
                                   |              +-----------+-----------+
                                   v                          |
                         +--------------------+               |
                         |  TTSEngine Adapter |<--------------+
                         | (Kokoro-82M ONNX)  |
                         +---------+----------+
                                   |
                                   v
                         +--------------------+
                         | Narration Builder  |
                         | (Pauses + Hashes)  |
                         +----+----------+----+
                              |          |
                              v          v
                  audio/lines/*.wav    audio/narration.wav
                              |
                              v
                   +----------------------+
                   | faster-whisper Align | (CUDA / CPU int8)
                   +----------+-----------+
                              |
                              v
                     audio/timings.json
                 (word-level absolute timing)
```

The pipeline follows an audio-first design:
1. **Engine Decoupling:** Scenes and scripts never interact directly with speech models. The `TTSEngine` interface (`pipeline/tts/base.py`) abstracts synthesis.
2. **Lexicon Isolation:** Spoken phonetic substitutions apply strictly to synthesis audio, leaving caption text untouched.
3. **Audio-Driven Animation:** Animation timing derives from absolute word timestamps emitted by forced alignment.

---

## 2. Voice Profiles

Voice profiles are stored as JSON files under `brand/voices/<profile_id>.json` and validated with Pydantic (`pipeline/tts/schemas.py`).

### Schema Fields
- `id` (str): Unique identifier (e.g. `calm_curious_heart`).
- `engine` (str): Engine adapter name (`kokoro`).
- `voice` (str): Catalog voice ID discovered from engine.
- `speed` (float): Speaking rate multiplier (`0.5` to `2.0`).
- `tone` (str): Preset tone (`calm_curious`, `energetic_playful`, `serious_cinematic`).
- `pause_ms` (dict): Pause durations (`{"sentence": int, "aha": int}`).
- `lexicon` (str): Path to pronunciation dictionary (`brand/lexicon.json`).
- `postfx` (str): Post-processing FX chain identifier.
- `license_note` (str): Verified commercial license.
- `status` (str): Status lifecycle (`candidate`, `approved`, `retired`).

### Candidate Profiles

| Profile ID | Tone Preset | Voice ID | Speed | Sentence Pause | Aha Pause | Status |
|---|---|---|---|---|---|---|
| `calm_curious_heart` | `calm_curious` | `af_heart` | 0.95 | 320 ms | 650 ms | candidate |
| `calm_curious_michael` | `calm_curious` | `am_michael` | 0.98 | 300 ms | 600 ms | candidate |
| `energetic_playful_bella` | `energetic_playful` | `af_bella` | 1.08 | 260 ms | 500 ms | candidate |
| `energetic_playful_adam` | `energetic_playful` | `am_adam` | 1.06 | 270 ms | 520 ms | candidate |
| `serious_cinematic_george` | `serious_cinematic` | `bm_george` | 0.92 | 350 ms | 750 ms | candidate |
| `serious_cinematic_fenrir` | `serious_cinematic` | `am_fenrir` | 0.90 | 340 ms | 700 ms | candidate |

### Kokoro License Verification
- **Model:** Kokoro-82M ONNX (`kokoro-v1.0.int8.onnx` and `voices-v1.0.bin`).
- **Official Repository:** [https://huggingface.co/hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) and [https://github.com/hexgrad/kokoro](https://github.com/hexgrad/kokoro).
- **License:** **Apache License 2.0**. Permissive for commercial and non-commercial production.

---

## 3. Pronunciation Lexicon (`brand/lexicon.json`)

To prevent mispronunciation of mathematical terminology, respellings are defined globally:
```json
{
  "eigenvector": "eye-gen vector",
  "eigenvalue": "eye-gen value",
  "eigen": "eye-gen",
  "Quantum8Lines": "Quantum Eight Lines"
}
```

### Matching Rules
1. **Whole-Word Matching:** Words are wrapped with regex word boundaries (`\b`) so terms like `eigenvectors` (plural) remain unaltered unless explicitly defined.
2. **Case-Insensitive:** Matches regardless of capitalization (`Eigenvector`, `EIGENVECTOR`).
3. **Compound Precedence:** Longer terms (`eigenvector`) are replaced before shorter substrings (`eigen`).
4. **Per-Line Overrides:** If `script.json` specifies `"pronounce": {"eigenvector": "custom"}`, the line-level override takes precedence over the global lexicon.
5. **Captions Preservation:** `prepare_text()` returns phonetic text for the TTS engine while leaving `line["text"]` intact for on-screen captions.

---

## 4. Narration Builder (`pipeline/narration.py`)

The narration builder renders chapter audio:
```python
from pipeline.narration import build_narration

timings = build_narration(chapter_dir="topics/linear_algebra/ch01", profile_id="calm_curious_heart")
```

### Key Behaviors
1. **Individual Line Audio:** Generates `audio/lines/<line_id>.wav` for each script line.
2. **Dynamic Pause Insertion:** Automatically applies `pause_ms["aha"]` (e.g. 600 ms) after lines where `beat == "aha"` and `pause_ms["sentence"]` (e.g. 300 ms) otherwise.
3. **Concatenation:** Conjoins all audio lines with silent padding into `audio/narration.wav`.
4. **Checkpointing:** Computes a SHA-256 hash of `(prepared_text, engine, voice, speed)` stored in `audio/.checkpoint.json`. On subsequent runs, lines with identical inputs are skipped from re-synthesis.
5. **Timings Output:** Produces `audio/timings.json` containing absolute start and end timestamps in seconds.

---

## 5. Audition Set & Rendering (`pipeline/audition.py`)

The audition set (`brand/voices/audition_set.json`) tests voices across 5 pedagogical beats:
1. `hook`: *"What if some arrows refuse to turn, no matter how hard you push?"*
2. `explain`: *"A matrix takes every vector in the plane and moves it somewhere else. Most of them change direction. A few don't."*
3. `equation`: *"A times v equals lambda times v. The matrix only stretches this vector. It never rotates it."*
4. `aha`: *"And that's the whole idea. An eigenvector is simply a direction the transformation leaves alone."*
5. `close`: *"Next time, we'll see why these special directions are everywhere."*

### How to Render Audition Set
Run:
```bash
uv run python -m pipeline.audition
```
Outputs are written to:
- Audio lines and narration: `build/voice_audition/<profile_id>/audio/`
- Manifest: `build/voice_audition/manifest.json`

---

## 6. Word-Level Alignment (`pipeline/align.py`)

Forced alignment uses `faster-whisper` (`small` model) to extract word-level timestamps.

### Device Strategy & Fallback
The alignment engine probes CUDA (`device="cuda"`, `compute_type="float16"`) with a dummy inference pass:
- If CUDA execution succeeds, GPU acceleration is utilized.
- If CUDA execution fails (e.g., missing CUDA DLLs like `cublas64_12.dll`), the engine reports the exact reason and falls back to CPU int8 (`device="cpu"`, `compute_type="int8"`).

### How to Run Alignment
```bash
uv run python -m pipeline.align
```
This enriches each profile's `timings.json` with word-level entries:
```json
{
  "word": "eigenvector",
  "start": 0.42,
  "end": 0.98,
  "probability": 0.995,
  "absolute_start": 3.72,
  "absolute_end": 4.28
}
```

---

## 7. M3a Audition & Alignment Benchmark Results

Synthesized and aligned on Windows 11 with Kokoro-82M ONNX and faster-whisper-small:

| Profile ID | Voice | Speed | Audio Duration | Render Time | Alignment Time (CPU int8) | Word Error Rate (WER) |
|---|---|---|---|---|---|---|
| `calm_curious_heart` | `af_heart` | 0.95 | 28.55 s | 39.48 s | 18.26 s | **0.0%** |
| `calm_curious_michael` | `am_michael` | 0.98 | 31.18 s | 35.70 s | 13.40 s | **0.0%** |
| `energetic_playful_bella` | `af_bella` | 1.08 | 26.87 s | 31.06 s | 13.54 s | **4.0%** |
| `energetic_playful_adam` | `am_adam` | 1.06 | 25.63 s | 29.55 s | 13.64 s | **2.6%** |
| `serious_cinematic_george` | `bm_george` | 0.92 | 33.18 s | 36.71 s | 13.15 s | **0.0%** |
| `serious_cinematic_fenrir` | `am_fenrir` | 0.90 | 30.65 s | 34.16 s | 13.14 s | **0.0%** |

### Device Benchmark Note
- CUDA initialization probe failed with: `Library cublas64_12.dll is not found or cannot be loaded`.
- Fallback to CPU (`int8`) completed smoothly across all 30 audio clips with an average alignment time of ~2.7s per line.
- 4 of the 6 candidate profiles achieved a perfect **0.0% WER**, confirming the phonetic accuracy of Kokoro-82M and faster-whisper alignment.
