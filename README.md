# Quantum8Lines

High-quality math and science explainer animations with 3Blue1Brown-style visual clarity and an automated generation pipeline.

---

## Quick Start

### 1. Environment Setup
Install dependencies and sync the pinned environment with [uv](https://docs.astral.sh/uv/):
```bash
uv sync
```

Prerequisites on system PATH:
- **Python 3.11**
- **FFmpeg & FFprobe**
- **LaTeX (MiKTeX / pdfTeX) & dvisvgm**

### 2. Render Layout Still Frames (16:9 & 9:16)
To verify frame safe-zones and region placement:
```bash
uv run python -c "from pathlib import Path; from core.layout import LAYOUT_169, LAYOUT_916, render_layout_still; render_layout_still(LAYOUT_169, Path('temp_renders/layout_16x9.png')); render_layout_still(LAYOUT_916, Path('temp_renders/layout_9x16.png'))"
```

### 3. Conform Brand Intro & Stings
Conform the master brand intro into 16:9 (1080p30) and 9:16 vertical stings (candidates A & B) with loudnorm analysis:
```bash
uv run python pipeline/conform.py
```

### 4. Run Test Suite
```bash
uv run pytest
```

---

## Repository Layout (SPEC.md Section 3)

```
quantum8lines-manim/
├── SPEC.md
├── brand/            intro/outro, logo, fonts, brand.json, mascot assets
├── core/
│   ├── tokens.py     design tokens loaded from brand/brand.json
│   ├── fonts.py      font registration and Inter typography helpers
│   ├── layout.py     16:9 + 9:16 layout engine, safe zones, LayoutTestScene
│   ├── components/   vectors, matrices, graphs, equations, callouts, mascot
│   ├── mathengine/   SymPy/NumPy fact computation + claim checkers
│   └── scene_base.py base Scene with audio-first timing
├── agents/           prompts (*.md) and schemas (*.py) per agent
├── pipeline/         stage runners, state machine, checkpointing, conform.py
├── topics/<topic>/
│   ├── bible.json
│   └── chapters/chNN/
│       ├── script.json
│       ├── facts.json
│       ├── storyboard.json
│       ├── scene.py
│       ├── audio/    (tts wavs, timings.json, mix)
│       ├── renders/  (916/, 169/)
│       ├── qa/       (reports, sample frames)
│       └── status.json
├── review_ui/        local approval gates (Streamlit)
├── tests/            automated tests and layout assertions
└── models/           offline TTS models (Kokoro-82M + voices)
```
