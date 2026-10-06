# Voice Profiles & Candidates

Follows **SPEC.md Section 10** and **Milestone M3a**.

The Quantum8Lines narration pipeline is strictly audio-first: narration durations establish the beat timing for animations. All narrator voices are fully synthetic, swappable, and validated via schema-enforced JSON profiles in `brand/voices/<id>.json`.

---

## 1. Engine & Commercial License Verification

- **Engine**: Kokoro-82M ONNX (`pipeline.tts.kokoro_engine.KokoroEngine`).
- **License**: **Apache License 2.0**.
  - Verified on the official model repository: [huggingface.co/hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) and [github.com/hexgrad/kokoro](https://github.com/hexgrad/kokoro).
  - Permissive for both research and commercial use.
- **Voice Discovery**: All candidate voice names are retrieved directly from the Kokoro voice style binary catalog (`models/voices-v1.0.bin`) via `kokoro.get_voices()`.

---

## 2. Candidate Profiles & Speed Justifications

| Profile ID | Voice | Preset Tone | Speed | Sentence Pause | Aha Pause | Justification |
|---|---|---|---|---|---|---|
| `calm_curious_heart` | `af_heart` | `calm_curious` | **0.95x** | 320 ms | 650 ms | Smooth, gentle feminine cadence. Speed 0.95x allows listeners to absorb dense mathematical concepts without sounding sluggish. |
| `calm_curious_michael` | `am_michael` | `calm_curious` | **0.98x** | 300 ms | 600 ms | Grounded, contemplative masculine voice with steady rhythm. Natural speaking pace for structured derivations. |
| `energetic_playful_bella` | `af_bella` | `energetic_playful` | **1.08x** | 220 ms | 500 ms | Bright, dynamic, and forward-moving. Speed 1.08x delivers punchy delivery suited for YouTube Shorts / Reels retention. |
| `energetic_playful_adam` | `am_adam` | `energetic_playful` | **1.06x** | 240 ms | 500 ms | Clear, articulate, high-energy masculine voice. Fast clip-through pacing for brisk visual hooks. |
| `serious_cinematic_george` | `bm_george` | `serious_cinematic` | **0.92x** | 380 ms | 750 ms | British received pronunciation with rich gravitas. Paced at 0.92x with extended pauses for dramatic mathematical build-ups. |
| `serious_cinematic_fenrir` | `am_fenrir` | `serious_cinematic` | **0.90x** | 400 ms | 800 ms | Deep, resonant baritone. Deliberate 0.90x pacing gives weighty authority to foundational theorems and philosophical conclusions. |

---

## 3. Pacing & Silence Architecture

Per SPEC Section 10:
- Standard sentence pauses: 220–400 ms.
- "Aha" payoff pauses: 500–800 ms preceding the critical insight, allowing visual animations to resolve cleanly before the narrator delivers the takeaway.
- Post-processing (`postfx`): Configured as `"warm_narration"` for downstream broadcast normalization.
