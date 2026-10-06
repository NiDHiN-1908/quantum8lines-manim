# Quantum8Lines: Project Spec v1

This file is the single source of truth. Every agent and every script follows it.
If code and this spec disagree, fix one of them in the same commit. Do not leave drift.

---

## 0. Rules for any agent working in this repo

1. **Never invent numbers.** Every number, coordinate, plot point, matrix, or formula result comes from `core/mathengine` (SymPy/NumPy), never from the LLM's head.
2. **Scenes draw, they do not compute.** Scene code reads values from `facts.json`. Numeric literals in scene code are limited to layout constants imported from `core.layout`.
3. **Audio first.** Narration is synthesized before animation. Animation timing is derived from audio segment durations.
4. **Gates are blocking.** A stage that fails its gate stops the pipeline and writes a report. It never "continues anyway".
5. **Everything is a file with a schema.** Agents exchange JSON validated by pydantic. Invalid output is retried at most 3 times, then the stage fails.
6. **Small, reviewable commits.** One milestone task per commit. No rewriting unrelated files.
7. **Ask when a decision is not in this spec.** Add it to section 19 (Open decisions), do not guess.

---

## 1. Mission and format

- **Channel:** Quantum8Lines. High-quality math/science explainers with 3Blue1Brown-style visual clarity and an original mascot.
- **Language:** English narration. Hindi may come later (section 17).
- **Unit of production:** a **Topic** is split into **Chapters**. Each chapter is a standalone short (target 45-90 s). After all chapters ship, the topic is compiled into one long video.
- **Outputs per chapter:** a 9:16 short (Instagram Reels / YouTube Shorts) and a 16:9 version (for the long video).
- **Outputs per topic:** one 16:9 long video (all chapters, bridges, optional synthesis chapter).

### Chapter structure (every chapter)

| Beat | Time | Purpose |
|---|---|---|
| Hook | 0-3 s | A visual or question that earns the next 10 s |
| Setup | 3-15 s | State the one idea and the question |
| Build | 15-55 s | Construct the idea visually, step by step |
| Aha | ~55-70 s | The payoff moment |
| Close | last 5-10 s | One-line recap, then a bridge to the next chapter (or CTA) |

Rule: **one idea per chapter.** Narration is about 100-180 words.

### Two cuts from one script

Every narration line carries a `cut` tag: `both` (default), `standalone_only` (e.g. "follow for more"), or `compilation_only` (e.g. bridge lines). The long video drops `standalone_only` lines and the repeated intro, and keeps `compilation_only` lines.

---

## 2. Tech stack (free)

| Need | Tool | Notes |
|---|---|---|
| Animation | Manim Community (target v0.20.x; legacy project used 0.19.1) | Upgrade in M0 and pin |
| Environment | `uv` + lockfile | Python 3.11; reproducible installs |
| Math truth | SymPy, NumPy | All facts computed here |
| LaTeX | MiKTeX (already installed), `dvisvgm` | For MathTex |
| Voice | Kokoro-82M ONNX (in `models/`) | Default voice chosen in M3 by A/B listening |
| Voice (optional) | Chatterbox or similar | Evaluate only if Kokoro sounds flat; confirm license on its repo first |
| Alignment | faster-whisper (`small` or larger) or a forced aligner against the known script | Evaluate in M3; `tiny` is not good enough |
| Captions | ASS subtitles (animated word highlight) | Burned in with FFmpeg |
| Assembly | FFmpeg | Loudness normalization, ducking, concat |
| Orchestration | Plain Python + pydantic | No agent framework until needed |
| Review UI | Streamlit (local) | Approval gates |
| Tests | pytest | Includes reference-frame tests |
| LLMs | Model-agnostic interface | Hosted free tier via Antigravity; Ollama local fallback. Check current free-tier limits before batch runs |

All tools must work offline except the LLM calls.

---

## 3. Repository layout

```
quantum8lines-manim/
├── SPEC.md
├── brand/            intro/outro, logo, fonts, brand.json, mascot assets
├── core/
│   ├── tokens.py     design tokens loaded from brand/brand.json
│   ├── layout.py     16:9 + 9:16 layout engine, safe zones
│   ├── components/   vectors, matrices, graphs, equations, callouts, mascot
│   ├── mathengine/   SymPy/NumPy fact computation + claim checkers
│   └── scene_base.py base Scene with audio-first timing
├── agents/           prompts (*.md) and schemas (*.py) per agent
├── pipeline/         stage runners, state machine, checkpointing
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
├── review_ui/
├── tests/
└── models/           Kokoro model + voices (not committed if large)
```

The leftover `src/` folder from the legacy layout is removed in M0. Legacy code is available at git tag `legacy-v0`.

---

## 4. Design system

### 4.1 Tokens
- Colors come from `brand/brand.json`. Dark background is `#0e0e11`.
- Keep the semantic roles from the legacy `colors.py`: `PRIMARY`, `SECONDARY`, `DYNAMIC`, `STATIC`, `HIGHLIGHT`. **M1 task:** read the legacy file (`git show legacy-v0:src/core/colors.py`) and document each role's meaning and value in `core/tokens.py`.
- Rule: a color always keeps its meaning across the whole channel. `DYNAMIC` means "changing", `STATIC` means "fixed", `HIGHLIGHT` means "look here".
- Never use raw Manim color names in scenes. Use tokens only.

### 4.2 Typography (all free, license files stored in `brand/fonts/`)
- Text and captions: **Inter** (bold for captions).
- Math: LaTeX default via MathTex.
- Reserved for later Hindi support: **Noto Sans Devanagari**.

### 4.3 Frames and layout
| Format | Pixels | Manim frame |
|---|---|---|
| 16:9 | 1920x1080 | width 14.222, height 8 |
| 9:16 | 1080x1920 | width 8, height 14.222 |

- The layout engine, not the scene, decides frame size. A scene declares **regions** (`title`, `stage`, `caption`, `footer`) and each layout places them.
- **9:16 safe zones (conservative starting values, verify against current platform UI before launch):** top 250 px, bottom 480 px, left/right 90 px kept free of essential content. Captions sit above the bottom zone.
- **16:9 title-safe margin:** 5% on all sides.
- Minimum on-screen text size (9:16, at 1080 px width): 48 px for captions and labels, 72 px for key words.

### 4.4 Motion language
- Default animation duration 0.6-1.0 s; transitions between ideas 0.4-0.6 s; easing `smooth` unless a rule says otherwise.
- At most **one thing moves at a time** unless the motion is the point.
- At most 7 distinct objects on screen at once (mascot and captions excluded).
- Every reveal is paired with narration that explains it, and the highlight lands on the spoken word.

### 4.5 Mascot
- Original character derived from the brain icon (`brand/brain_icon.svg`), built as an SVG-based Mobject with a small set of states: `idle`, `blink`, `think`, `surprised`, `point`.
- Appears at most 3 times per chapter and is never over the stage region. It never carries essential information.
- Do not copy any existing channel's characters.

### 4.6 Intro / outro
- Final intro file: `brand/Quantum8Line_Intro.mp4` (1280x720, 24 fps, ~10 s, with audio). The legacy 480p15 renders in `brand/` are drafts and are not used in production.
- The intro plays once at the start of standalone shorts. For 9:16, use a 2-3 s sting derived from the same assets (M1 task). In the long video it plays once at the start.
- Intro audio is part of the loudness mix (section 11).

---

## 5. Data contracts (pydantic models live in `agents/`)

### 5.1 `bible.json` (per topic)
```json
{
  "topic": "Eigenvectors",
  "audience": "high school to first-year university, comfortable with basic algebra",
  "arc": "hook, build, payoff across chapters",
  "notation": {"matrix": "A", "vector": "v", "eigenvalue": "λ"},
  "chapters": [
    {"id": "ch01", "title": "...", "one_idea": "...", "question_it_raises": "..."}
  ],
  "prereqs": [],
  "sources": ["textbook or reference names used to fact-check"]
}
```

### 5.2 `script.json`
```json
{
  "chapter": "ch01",
  "lines": [
    {"id": "l01", "text": "...", "beat": "hook", "cut": "both",
     "claims": ["c1"], "pronounce": {"eigenvector": "EYE-gen-vector"}}
  ]
}
```

### 5.3 `facts.json` (computed, never written by an LLM)
```json
{
  "claims": [
    {"id": "c1", "type": "eigenpair", "matrix": [[2,1],[0,3]],
     "vector": [1,0], "value": 2, "verified": true}
  ],
  "values": {"A": [[2,1],[0,3]], "eigvals": [2,3]}
}
```

### 5.4 `storyboard.json`
```json
{
  "chapter": "ch01",
  "beats": [
    {"id": "b01", "line_ids": ["l01"], "regions": {"stage": "..."},
     "actions": [{"op": "show", "component": "VectorField", "args_from": "values.A"}],
     "expect": {"visible": ["vector_v"], "text": "vector stays on its line"}}
  ]
}
```
Every beat must reference script lines and facts, never raw numbers.

---

## 6. Agents

| Agent | Input | Output | Must not |
|---|---|---|---|
| Curriculum planner | topic, audience | `bible.json` | Create chapters with more than one idea |
| Scriptwriter | bible + chapter spec | `script.json` | State a number; write math claims without a claim id |
| Math verifier | `script.json` claims | `facts.json` | Pass a claim it could not check; mark it `unverifiable` instead |
| Storyboarder | script + facts | `storyboard.json` | Use components that are not in the library |
| Scene coder | storyboard + component docs | `scene.py` | Use numeric literals; import anything outside `core` |
| QA agent | renders + storyboard | `qa/report.json` | Block on a vision-model opinion (advisory only) |
| Publisher | final chapter/topic | title, description, tags, thumbnail brief | Claim features not in the video |

Each agent prompt lives in `agents/<name>.md` with a fixed structure: role, inputs, output schema, constraints, 2 worked examples, and failure behavior. Prompts are versioned in git.

---

## 7. Math engine and claim checking

`core/mathengine` offers one checker per claim type. Start with:

| Claim type | Check |
|---|---|
| `equation_true` | substitute and simplify with SymPy |
| `solution_set` | solve symbolically and compare |
| `eigenpair` | verify `A @ v == λ * v` exactly (rational arithmetic where possible) |
| `intersection` | solve the system, compare to plotted points |
| `derivative` / `integral` | differentiate/integrate symbolically and compare |
| `value_at` | evaluate expression at a point |
| `plot_matches` | sample the plotted function and compare to SymPy within tolerance |

Rules:
- Prefer exact (rational/symbolic) arithmetic. Use floats only for plotting.
- Components that draw math take **objects from `facts.json`**, so drawing from a wrong number is not possible by construction.
- New claim types are added with unit tests first.

---

## 8. Pipeline stages and state

Stages run in order. Each writes its artifact, a hash of its inputs, and updates `status.json`. On re-run, a stage whose input hash is unchanged is skipped (checkpointing). Any stage can be re-run alone.

```
plan -> script -> verify -> storyboard -> tts -> align -> code -> test_render
     -> qa_visual -> final_render -> mix -> captions -> assemble -> export -> review
```

`status.json` records, per stage: `pending | running | passed | failed | needs_human`, timestamps, and artifact paths.

Auto-fix loop: for `code` and `test_render` failures, the scene coder gets the error and may retry up to 3 times. After that: `failed` with a report.

---

## 9. Quality gates (blocking)

| Gate | After | Pass criteria |
|---|---|---|
| G1 Script | script | schema valid; word count in range; every claim id exists; beat order correct |
| G2 Math | verify | 100% of claims `verified` (none failed or unverifiable) |
| G3 Plan review | storyboard | **human** approves script + storyboard in review UI |
| G4 Code | code | lints clean (no numeric literals outside layout constants, no raw colors, imports only from `core`); scene constructs without error |
| G5 Render test | test_render | low-res render succeeds; no empty frames; duration within ±0.3 s of audio |
| G6 Visual | qa_visual | at each beat's keyframe: all objects inside safe area; no overlapping text/objects; min text size; contrast above threshold; every `expect.visible` item present |
| G7 Audio | mix | integrated loudness within target; no clipping |
| G8 Final review | export | **human** watches both versions and approves |

The vision model may add notes to G6, but only deterministic checks can fail a gate. Vision notes go to the human reviewer.

---

## 10. Audio-first timing

1. TTS renders each line to its own wav; durations go in `timings.json`.
2. Alignment produces word-level timestamps for captions and highlight cues.
3. `core/scene_base.py` exposes `self.beat("b01")` which advances to that beat's audio start/end. Animation `run_time` and waits are computed to fill the beat, never hard-coded.
4. If an animation cannot fit its audio window, the storyboard is revised (not the audio stretched).

### Voice
- Default Kokoro voice chosen in M3 by listening to 5 candidates on the same 3 sample lines.
- Pronunciation dictionary `brand/lexicon.json` maps terms to respellings; per-line overrides come from `script.json`.
- Add 0.2-0.4 s of silence between sentences, longer (0.6 s) before the aha.

### Loudness and music
- Target about **-14 LUFS integrated**, true peak at or below **-1 dBTP**, for all exports.
- Background music: only royalty-free tracks whose license is recorded in `brand/music/LICENSES.md`; ducked under voice with FFmpeg sidechain compression. Music volume sits clearly below voice.
- Sound design: a small library of soft whooshes/clicks for reveals; no more than one effect per second.

---

## 11. Captions

- Generated as ASS with word-by-word highlight using aligned timestamps.
- Style: Inter Bold, white text, active word in `HIGHLIGHT`, dark outline, max 2 lines, 3-5 words visible at a time.
- Position: inside the safe zone, above the bottom reserved area (9:16) or lower third (16:9).
- Captions are also exported as a plain `.srt` for YouTube upload.
- Captions must match the final script text exactly; a diff check runs in G7.

---

## 12. Assembly and export

| Item | Standard |
|---|---|
| Frame rate | 30 fps for all final renders |
| 9:16 export | 1080x1920, H.264, AAC 48 kHz, MP4 |
| 16:9 export | 1920x1080, same codecs |
| Intro | conformed to the target resolution and fps with FFmpeg; audio normalized with the rest |
| Short file name | `<topic>_<chNN>_<slug>_916.mp4` |
| Long file name | `<topic>_full_169.mp4` |

Long video compile: intro once, chapters in order (using the 16:9 renders, `standalone_only` lines removed, `compilation_only` lines kept), chapter title cards (optional), optional synthesis chapter, end card.

Final renders happen only after G3 and G4 pass. Day-to-day iteration uses low-res test renders.

---

## 13. Review UI (Streamlit, local)

Pages:
1. **Topic plan:** chapters, arc, notation; approve or edit.
2. **Script + facts:** script lines beside their verified claims; approve (G3).
3. **Storyboard:** beats and expected visuals.
4. **Preview:** play the test render with the QA report and sample frames.
5. **Final:** both exports, loudness report, caption check; approve (G8).
6. **Status board:** every chapter, every stage, with failed gates highlighted and a button to re-run a single stage.

---

## 14. Testing

- **Unit tests:** every claim checker (positive and negative cases), layout engine safe-zone math, timing calculations.
- **Component tests:** each component renders at both aspect ratios without exceptions.
- **Reference-frame tests:** render a fixed frame of each component and compare to a stored image within a tolerance. Update references only in a dedicated commit.
- **Lint tests:** the G4 linter has its own tests.
- CI is a single command: `uv run pytest` (local, no hosted CI needed at first).

---

## 15. Licensing and platform checklist (complete before first upload)

- [ ] Font licenses stored in `brand/fonts/`
- [ ] Music tracks and licenses in `brand/music/LICENSES.md`
- [ ] TTS model license read on the model's own repository, and noted here
- [ ] YouTube policy check: disclosure of synthetic/altered content, and monetization rules for automated or repetitive content (rules change; read the current ones)
- [ ] Instagram safe-zone values re-verified against the current app UI
- [ ] Source list for factual claims in each topic recorded in `bible.json`

---

## 16. Milestones and definition of done

| ID | Milestone | Done when |
|---|---|---|
| M0 | Environment | `uv` project, pinned Manim 0.20.x and deps, `legacy` `src/` removed, hello scene renders in 16:9 and 9:16 |
| M1 | Design system | tokens, layout engine with safe zones, intro/outro integration, 9:16 sting, font setup, tests green |
| M2 | Components + math engine | vector, matrix, graph, equation, callout, mascot components; claim checkers with tests; reference-frame tests |
| M3 | Audio pipeline | TTS, lexicon, alignment, ASS captions, loudness mix; a sample line set sounds good to you |
| M4 | QA gates | G4-G7 implemented and demonstrably catching seeded errors (wrong number, off-screen object, overlapping text) |
| M5 | Agents | all agents produce schema-valid output; prompts versioned; end-to-end dry run on a stub topic |
| M6 | Pilot chapter | one chapter fully through all gates, both formats, approved by you |
| M7 | Pilot topic | all chapters of the pilot topic + long video compile |
| M8 | Review UI + publisher | UI covers all gates; publisher outputs titles/descriptions/thumbnail briefs |

Do not start a milestone before the previous one is done. Seeded-error tests in M4 are the proof that the quality system works.

---

## 17. Hindi readiness (design now, build later)

- Narration text lives only in `script.json`, never in scene code.
- Fonts support Devanagari (Noto Sans Devanagari).
- Text boxes leave 30% extra width.
- Lexicon is stored per language.
- Math labels use universal notation.

---

## 18. Proposed pilot topic (confirm before M5)

**Eigenvectors**, six short chapters. Working titles taken from the legacy file names: refusal (a vector that keeps its direction), the world (transformations), repetition, decomposition, formalism, inevitability. Final chapter list is produced by the curriculum planner and approved by you in the review UI.

---

## 19. Open decisions

- [ ] Pilot topic confirmed
- [ ] Default Kokoro voice (decided by listening in M3)
- [ ] Alignment method (whisper size vs forced aligner), decided in M3 on accuracy and speed
- [ ] Background music source
- [ ] Whether the long video gets a synthesis chapter by default
- [ ] LLM provider order and local fallback model
- [ ] Hardware limits (render time per chapter) measured in M0
