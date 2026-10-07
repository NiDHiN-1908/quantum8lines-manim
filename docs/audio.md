# Audio Pipeline & Voice Lab Documentation

This document describes the audio pipeline architecture, voice profiles, pronunciation lexicon, narration generation, post-processing FX, loudness normalization, ducked mixing, word-level alignment, automated captions (ASS and SRT), and the interactive Voice Lab review application for Quantum8Lines animations, adhering to **SPEC.md Sections 4, 10, 11, 12, 14, and Milestones M3a & M3b**.

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
                              +--------------------+
                              |                    |
                              v                    v
                   +----------------------+   +-----------------------+
                   | faster-whisper Align |   |  Audio FX & Loudnorm  |
                   | (CUDA / CPU int8)    |   | (-14 LUFS, -1.5 dBTP) |
                   +----------+-----------+   +-----------+-----------+
                              |                           |
                              v                           v
                     audio/timings.json        audio/narration_postfx.wav
                 (word-level absolute timing)             |
                              |                           v
                              |               +-----------------------+
                              |               | Ducked Mix with Music |
                              |               +-----------------------+
                              v
                  +-----------------------+
                  |  Captions Generator   |
                  | (ASS Highlight + SRT) |
                  +-----------+-----------+
                              |
                              v
                  Burn-in / Video Assembly
```

The pipeline follows an audio-first design:
1. **Engine Decoupling:** Scenes and scripts never interact directly with speech models. The `TTSEngine` interface (`pipeline/tts/base.py`) abstracts synthesis.
2. **Lexicon Isolation:** Spoken phonetic substitutions apply strictly to synthesis audio, leaving caption text untouched.
3. **Audio-Driven Animation:** Animation timing derives from absolute word timestamps emitted by forced alignment.
4. **Broadcast Standard Audio:** Loudness is normalized to -14 LUFS integrated with true peak target -1.5 dBTP (landing $\le -1.0$ dBTP).
5. **Dynamic Captions:** Burned ASS subtitles provide word-by-word highlighted text in the `HIGHLIGHT` token color.

---

## 2. Voice Profiles

Voice profiles are stored as JSON files under `brand/voices/<profile_id>.json` and validated with Pydantic (`pipeline/tts/schemas.py`).

### Schema Fields
- `id` (str): Unique identifier (e.g. `calm_curious_heart`).
- `engine` (str): Engine adapter name (`kokoro`).
- `voice` (str): Catalog voice ID discovered dynamically from engine.
- `speed` (float): Speaking rate multiplier (`0.5` to `2.0`).
- `tone` (str): Preset tone (`calm_curious`, `energetic_playful`, `serious_cinematic`).
- `pause_ms` (dict): Pause durations (`{"sentence": int, "aha": int}`).
- `lexicon` (str): Path to pronunciation dictionary (`brand/lexicon.json`).
- `postfx` (str): Post-processing FX chain identifier (`warm_narration`, `clean`).
- `license_note` (str): Verified commercial license.
- `status` (str): Status lifecycle (`candidate`, `approved`, `retired`).

### Candidate Profiles

| Profile ID | Tone Preset | Voice ID | Speed | Sentence Pause | Aha Pause | PostFX Preset | Status |
|---|---|---|---|---|---|---|---|
| `calm_curious_heart` | `calm_curious` | `af_heart` | 0.95 | 320 ms | 650 ms | `warm_narration` | candidate |
| `calm_curious_michael` | `calm_curious` | `am_michael` | 0.98 | 300 ms | 600 ms | `warm_narration` | candidate |
| `energetic_playful_bella` | `energetic_playful` | `af_bella` | 1.08 | 260 ms | 500 ms | `warm_narration` | candidate |
| `energetic_playful_adam` | `energetic_playful` | `am_adam` | 1.06 | 270 ms | 520 ms | `warm_narration` | candidate |
| `serious_cinematic_george` | `serious_cinematic` | `bm_george` | 0.92 | 350 ms | 750 ms | `warm_narration` | candidate |
| `serious_cinematic_fenrir` | `serious_cinematic` | `am_fenrir` | 0.90 | 340 ms | 700 ms | `warm_narration` | candidate |

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

## 5. Loudness Normalization & PostFX (`pipeline/audio_fx.py`)

Per **SPEC Section 10**:
- Integrated Loudness Target: **-14 LUFS integrated** ($\pm 1.0$ LU).
- Maximum True Peak: target **-1.5 dBTP** (so real exports land at or below **-1.0 dBTP**, never clipping).

### PostFX Filter Presets
Defined in `pipeline/audio_fx.py` as transparent FFmpeg filter chains:

1. **`clean`** (`highpass=f=70`):
   - Removes sub-bass rumble, ambient low-end vibration, and microphone handling noise below human vocal fundamentals (70 Hz) while preserving the natural spoken voice.
2. **`warm_narration`** (`highpass=f=70,equalizer=f=200:t=q:w=1.0:g=1.5,acompressor=threshold=-18dB:ratio=2.5:attack=20:release=150`):
   - `highpass=f=70`: High-pass rumble filter.
   - `equalizer=f=200:t=q:w=1.0:g=1.5`: Adds subtle warmth in the lower midrange (200 Hz with Q=1.0, +1.5 dB) for an intimate, pedagogical presence.
   - `acompressor`: Gentle, transparent compression (2.5:1 ratio, 20 ms attack, 150 ms release, -18 dB threshold) smoothing spoken dynamics without audible breathing or pumping artifacts.

### Two-Pass Loudness Normalization (`normalize`)
- **Target:** -14 LUFS integrated ($\pm 1.0$ LU) and target True Peak **-1.5 dBTP** so exports reliably land at or below -1.0 dBTP.
- **Pass 1:** Analyzes audio with `loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json`.
- **Pass 2:** Applies linear normalization using measured `input_i`, `input_tp`, `input_lra`, `input_thresh`, and `target_offset`.
- Automatically retains video streams (`-c:v copy`) when normalizing video files (e.g. intros).

### Ducked Audio Mixing (`mix`)
When background music is added:
- Music is attenuated (default `-18 dB`) so it never competes with the voice.
- An FFmpeg `sidechaincompress` filter dynamically ducks the music by 4:1 whenever voice activity is present (attack 50 ms, release 300 ms).
- Mixed with `amix` and normalized to -14 LUFS.

### Conformed Intro Video Loudness Normalization
All intro assets in `build/` are normalized to -14 LUFS with -1.5 dBTP target:
- `build/intro_169.mp4`: -33.09 LUFS $\to$ **-14.18 LUFS** (True Peak: -1.47 dBTP)
- `build/intro_916_candidate_a.mp4`: -32.67 LUFS $\to$ **-13.94 LUFS** (True Peak: -1.61 dBTP)
- `build/intro_916_candidate_b.mp4`: -33.59 LUFS $\to$ **-14.09 LUFS** (True Peak: -1.56 dBTP)

---

## 6. Captions Pipeline (`pipeline/captions.py`)

Follows **SPEC Section 11**:
- Format: Advanced SubStation Alpha (`.ass`) with word-by-word highlight, and plain `.srt`.
- Typography: **Inter Bold**, white primary text (`&H00FFFFFF&`), active word highlighted in `HIGHLIGHT` token color (`#83c167` $\to$ `&H0067C183&`), dark background outline (`&H00110E0E&`).
- Chunking: 3 to 5 words visible at any given moment, at most 2 lines.
- Safe-Zone Positioning: Positioned strictly inside the `caption` region:
  - In **16:9** (`PlayRes: 1920x1080`): Centered horizontally, bottom margin 148 px (lower third, below stage and above footer).
  - In **9:16** (`PlayRes: 1080x1920`): Centered horizontally, bottom margin 568 px (comfortably above the 480 px reserved bottom UI area).
- Text Verification (`check_caption_text`): Asserts that extracted caption words match script words 100% ignoring case and punctuation. Emits a unified diff on mismatch.
- Burn-In Helper (`burn_captions`): Uses FFmpeg's `subtitles` filter with `fontsdir=brand/fonts` and robust Windows path escaping (colons and backslashes escaped).

---

## 7. Word-Level Alignment (`pipeline/align.py`)

Forced alignment uses `faster-whisper` (`small` model) to extract word-level timestamps.

### Device Strategy & Fallback
The alignment engine probes CUDA (`device="cuda"`, `compute_type="float16"`) with a dummy inference pass:
- If CUDA execution succeeds, GPU acceleration is utilized.
- If CUDA execution fails (e.g., missing CUDA DLLs like `cublas64_12.dll`), the engine reports the exact reason and falls back to CPU int8 (`device="cpu"`, `compute_type="int8"`).

### How to Run Alignment
```bash
uv run python -m pipeline.align
```

---

## 8. Interactive Voice Lab (`review_ui/voice_lab.py`)

A local Streamlit application for reviewing, blind-testing, approving, and assigning voice profiles.

### How to Run Voice Lab
```bash
uv run streamlit run review_ui/voice_lab.py
```

### Sections & Capabilities
1. **Audition Tab:**
   - Displays all 5 audition lines (`hook`, `explain`, `equation`, `aha`, `close`).
   - Audio players for every candidate profile with a toggle between **Raw** and **PostFX (warm_narration)**.
   - One-click re-rendering of audition clips.
2. **Blind Test Tab:**
   - Shuffles profiles under anonymous labels (`Voice A`, `Voice B`, ...).
   - Collects listener name, naturalness ratings (1 to 5), and "would keep watching" (Yes/No).
   - Supports uploading real human audio clips for baseline comparison.
   - Reveals voice mapping only after ratings are saved to `brand/voices/scores.json`.
3. **Results & Acceptance Tab:**
   - Table of listeners, mean naturalness, keep-watching percentage, and pass/fail status.
   - **Acceptance Rule (Documented Starting Assumptions):**
     - Minimum **5 listeners**
     - Mean naturalness $\ge$ **4.0 / 5.0**
     - Keep-watching rate $\ge$ **70%**
4. **Approve Profile Tab:**
   - Approves profiles that meet the acceptance criteria.
   - Allows "Approve with Override", requiring a documented non-empty reason stored in the profile JSON.
5. **Assign to Topic Tab:**
   - Restricts assignment strictly to approved profiles.
   - Writes `voice_profile` into the target topic's `topics/<topic>/bible.json` (creating a minimal `bible.json` if absent).
