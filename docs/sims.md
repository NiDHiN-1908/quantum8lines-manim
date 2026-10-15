# Procedural Simulation Shorts Architecture (Milestone P1)

This document describes the design, architecture, rendering pipeline, procedural sound engine, and runner for standalone procedural simulation shorts (such as the Ellipse Billiards prototype) in Quantum8Lines.

---

## 1. Architectural Overview

Procedural simulation shorts generate mesmerizing, mathematically exact vertical (9:16) animations with zero external audio assets and no discrete numerical integration drift.

```
+-------------------------------------------------------------+
|              Simulation Specification                       |
|           (sims/<sim_name>/sim_spec.json)                   |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|              Analytical Physics Simulation                  |
|               (core/sims/ellipse_billiards.py)              |
|        - Exact ray-ellipse quadratic intersections          |
|        - Inward normal specular reflections                 |
|        - Deterministic events: launch, bounce, pass_focus   |
+-------------------------------------------------------------+
               /                              \
              v                                v
+-----------------------------+  +----------------------------+
|     Fast Cairo Renderer     |  |   Procedural Audio Engine  |
|    (core/sims/render.py)    |  |    (core/sims/sound.py)    |
| - pycairo direct raster     |  | - Pentatonic sine pings    |
| - scipy Gaussian glow       |  | - Stereo panning by pos x  |
| - Fading motion trails      |  | - 1/sqrt(N) gain scaling   |
| - Rawvideo pipe to FFmpeg   |  | - Focal convergence chime  |
+-----------------------------+  +----------------------------+
               \                              /
                v                            v
+-------------------------------------------------------------+
|                 Muxing & QA Runner                          |
|                (pipeline/sim_run.py)                        |
| - FFmpeg stream mux (video + audio)                         |
| - Two-pass loudnorm (-14 LUFS, <= -1.5 dBTP)                |
| - G7 audio quality & clipping verification                  |
| - Representative stage frame extraction                     |
| -> temp_renders/sim/<sim_name>_916_<quality>.mp4            |
+-------------------------------------------------------------+
```

---

### 2. Renderer Technology Choice: pycairo + NumPy vs. Manim

For procedural physics simulations involving dozens of particles and fading trails at 30 fps, **`pycairo` with NumPy and FFmpeg direct piping** was chosen over Manim for the following reasons:

1. **Zero Mobject Allocation Overhead:**
   Manim is designed for declarative vector animations, allocating Python objects (`Circle`, `Line`, `VGroup`) for every element on every frame. When rendering 55 balls with 14-segment fading trails, Manim would manage over 800 mobjects per frame, incurring severe garbage collection overhead. Cairo draws directly to memory buffers with native C speed.
2. **Direct Memory Mapping via FFmpeg Pipe:**
   Cairo's `ImageSurface(FORMAT_ARGB32)` stores pixels in native contiguous memory (`bgra` on little-endian x86/Windows). The runner streams `surface.get_data()` directly into FFmpeg's `stdin` via `-f rawvideo -pix_fmt bgra`, eliminating all disk I/O and frame PNG saving.
3. **Static Architecture Caching & Half-Resolution Glow:**
   The background radial vignette, faint glass fill, and static ellipse outline/foci are pre-rendered once into a cached static layer surface (`self.static_surface`), blitted in <1 ms per frame. The glow layer is processed at half resolution (540x960) with `scipy.ndimage.gaussian_filter`, achieving a 3x speedup.
4. **Rendering Performance Comparison (Before vs. After Optimization):**
   - **Video Render Time (1080x1920, 32.0s, 960 frames):** reduced from **235.92 s** to **81.32 s** (target <= 90s achieved).
   - **Total Pipeline Time:** reduced from **248.12 s** to **93.06 s**.

---

## 3. The Ellipse Billiards Physics Simulation

### Mathematical Foundation
The ellipse is defined with semi-minor axis $a = 0.6$ (horizontal) and semi-major axis $b = 0.8$ (vertical):
$$\frac{x^2}{a^2} + \frac{y^2}{b^2} = 1$$

Foci lie on the vertical axis at distance $c = \sqrt{b^2 - a^2} \approx 0.52915$:
$$F_1 = (0, -c), \quad F_2 = (0, c)$$

Balls are launched from $F_1$ at evenly spread angles with unit speed ($v = 1.0$).

### Invariant Theorems of Conic Billiards
1. **Reflection Law:**
   At any boundary point $P(x, y)$, the inward normal is $\hat{n} = -\frac{\nabla f}{\|\nabla f\|}$. The reflected velocity is:
   $$\vec{v}_{out} = \vec{v}_{in} - 2(\vec{v}_{in} \cdot \hat{n})\hat{n}$$
   The angle of incidence equals the angle of reflection within $10^{-16}$.
2. **Iso-Temporal Focal Convergence:**
   By the reflective property of ellipses, any ray emitted from focus $F_1$ reflecting off the wall passes through the opposite focus $F_2$. Furthermore, the sum of focal radii is constant:
   $$\|P - F_1\| + \|F_2 - P\| = 2b$$
   Since balls move at unit speed $v = 1$, **every ball launched from $F_1$ reaches $F_2$ at the exact same instant**:
   $$t_{F_2} = t_{\text{launch}} + 2b$$
3. **Second Bounce Convergence:**
   After passing $F_2$, the rays bounce a second time and reflect directly toward $F_1$, reaching $F_1$ at:
   $$t_{F_1} = t_{\text{launch}} + 4b$$

### Critical Rule: Physics Code is Never Written by an LLM
All physical laws, differential equations, collision responses, and geometric solvers in Quantum8Lines are implemented deterministically in pure Python by human engineers or verified math libraries. LLMs are never used to generate physics engines or dynamical system equations, preventing hallucinated mechanics or non-physical drift.

---

## 4. Procedural Audio Synthesis & Sound Polish (Milestone P2a.1)

Audio is generated entirely algorithmically without external audio assets or samples:

### Timbre Palettes (`core/sims/sound/palettes.py`)
1. **`pluck` (Karplus-Strong):**
   Physical modeling of a plucked string with tuned delay-line IIR filter and a 3.5 ms shaped noise click transient for bright, tactile excitation.
2. **`marimba` (Additive with Inharmonic Partials):**
   Acoustic simulation of an undercut wooden xylophone bar with partials at $1.0\times, 3.98\times, 9.25\times, 13.5\times$ and a short mallet attack click.
3. **`bell` (FM Synthesis):**
   Chowning frequency modulation with an inharmonic modulation ratio ($1.414\times$) and decaying modulation index envelope.
4. **`glass` (High Sine Cluster with Shimmer):**
   High crystalline cluster of detuned sines ($1.000\times, 1.004\times, 1.503\times, 2.001\times, 2.752\times$) with 4.0 Hz beating shimmer and tick transient.
5. **`legacy_ping`:**
   Preserved legacy ping from Milestone P1 (sine wave with 2 ms attack and 0.08s exponential decay).
6. **`pad` (Stage-Rising Atmospheric Drone):**
   Warm ambient pad chord stepping upward through scale degrees across stages with smooth crossfades and subtle tremolo.

### Musical Mapping
- **Arpeggiated First Bounces:** Across each stage, the first bounces of balls are sorted chronologically by wall collision time and assigned ascending scale degrees across the octave span, producing an upward arpeggio on each launch wave.
- **F2 Convergence Chord & Visceral Low Thump:** When balls converge at focus $F_2$, a lush multi-voice chord (the active ball pitches) sounds simultaneously with a low-frequency sine sweep thump (80 Hz down to 40 Hz).
- **Count-Increase Chime:** Each stage transition triggering an increased ball count sounds a bright rising two-note chime.
- **Master High-Shelf EQ:** Master chain incorporates a gentle biquad IIR high-shelf boost (+3.0 dB above 3 kHz) for high presence and sparkle, ensuring the measured spectral centroid of the first 20s comfortably exceeds 1.5 kHz.
- **Energy Conservation in Dense Moments:** Gain scales as $1/\sqrt{M}$ where $M$ is the number of simultaneous onsets within a 35 ms window, ensuring dense clusters (up to 55 balls) never clip.

---

## 5. Objective Audition Report (Milestone P2a.1)

Rendered via `python -m pipeline.sound_audition sims/ellipse_billiards` across all 10 presets for both key segments: `0-8s (early)` and `20-32s (dense)`:

| Preset | Segment | Palette | Scale | Integrated (LUFS) | True Peak (dBTP) | LRA (LU) | Spectral Centroid (Hz) | Onsets / sec | Peak Polyphony |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pluck+pentatonic` | 0-8s (early) | pluck | pentatonic_major | -14.96 | -0.81 | 1.50 | 1032.2 | 2.12 | 6 |
| `pluck+pentatonic` | 20-32s (dense) | pluck | pentatonic_major | -14.99 | -0.52 | 2.80 | 10095.1 | 28.58 | 24 |
| `marimba+pentatonic` | 0-8s (early) | marimba | pentatonic_major | -14.10 | -1.50 | 0.50 | 614.7 | 2.12 | 6 |
| `marimba+pentatonic` | 20-32s (dense) | marimba | pentatonic_major | -14.36 | -1.48 | 4.00 | 5322.9 | 28.58 | 24 |
| `bell+lydian` | 0-8s (early) | bell | lydian | -14.00 | -1.98 | 2.00 | 959.0 | 2.12 | 6 |
| `bell+lydian` | 20-32s (dense) | bell | lydian | -14.01 | -2.31 | 3.80 | 4522.0 | 28.58 | 24 |
| `glass+whole-tone` | 0-8s (early) | glass | whole_tone | -14.15 | -1.50 | 0.60 | 600.1 | 2.12 | 6 |
| `glass+whole-tone` | 20-32s (dense) | glass | whole_tone | -14.26 | -1.45 | 3.10 | 4222.9 | 28.58 | 24 |
| `marimba+minor with reverb` | 0-8s (early) | marimba | natural_minor | -14.55 | -1.50 | 1.40 | 500.6 | 2.12 | 6 |
| `marimba+minor with reverb` | 20-32s (dense) | marimba | natural_minor | -14.36 | -1.48 | 3.70 | 2878.4 | 28.58 | 24 |
| `pluck+major with grid quantization` | 0-8s (early) | pluck | major | -14.94 | -0.68 | 1.30 | 952.0 | 2.12 | 6 |
| `pluck+major with grid quantization` | 20-32s (dense) | pluck | major | -14.96 | -1.10 | 3.40 | 8007.1 | 28.58 | 24 |
| `kalimba-like pluck with pentatonic` | 0-8s (early) | pluck | pentatonic_major | -14.97 | -0.76 | 1.40 | 1122.8 | 2.12 | 6 |
| `kalimba-like pluck with pentatonic` | 20-32s (dense) | pluck | pentatonic_major | -15.24 | -0.46 | 3.10 | 9827.4 | 28.58 | 24 |
| `glass+major with riser` | 0-8s (early) | glass | major | -14.30 | -1.50 | 0.90 | 594.5 | 2.12 | 6 |
| `glass+major with riser` | 20-32s (dense) | glass | major | -14.38 | -1.48 | 3.40 | 3942.0 | 28.58 | 24 |
| `pluck+lydian with chord payoff` | 0-8s (early) | pluck | lydian | -14.95 | -0.81 | 1.40 | 1009.2 | 2.12 | 6 |
| `pluck+lydian with chord payoff` | 20-32s (dense) | pluck | lydian | -15.30 | -1.08 | 3.10 | 7836.2 | 28.58 | 24 |
| `legacy_ping` | 0-8s (early) | legacy_ping | pentatonic_major | -14.26 | -1.50 | 1.20 | 278.9 | 2.12 | 6 |
| `legacy_ping` | 20-32s (dense) | legacy_ping | pentatonic_major | -14.40 | -1.49 | 2.90 | 6047.8 | 28.58 | 24 |

---

## 6. Sound Lab (`review_ui/sound_lab.py` and `sound_lab_logic.py`)

Follows the Voice Lab pattern with pure business logic and Streamlit UI:
- **Audition Mode:** Players with preset names visible and objective metrics displayed.
- **Blind Evaluation Mode:** Anonymous shuffled labels (Preset A, Preset B, ...), 1-5 pleasantness rating, and "would keep watching" boolean.
- **Strict Data Policy:** No human listener evaluations, ratings, or scores are invented. The Sound Lab creates `sound_scores.json` only when real human evaluators rate presets.
- **Status Tracking:** Presets remain in `"unapproved_default"` or `"candidate"` until real human panels approve them.

---

## 7. Safe Area, Stage Fill (Gate S3b), and Layout Compliance

The animation adheres strictly to the vertical layout standard `LAYOUT_916` defined in `core/layout.py`:
- **Canvas:** 1080 x 1920 pixels (9:16 aspect ratio).
- **Safe Margins:** Top 250 px, Bottom 480 px, Left/Right 90 px.
- **Safe Box:** $X \in [90, 990]$, $Y \in [250, 1440]$.
- **Title:** `"Where do they all meet?"` rendered at 60 px Inter Bold, centered horizontally at $X = 540$ px, $Y = 360$ px. Bounding box $X \in [165, 915]$, $Y \in [305, 360]$ (100% inside safe area).
- **Counter:** `"Balls: <count>"` rendered at 48 px Inter Bold, centered at $X = 540$ px, $Y = 430$ px. Bounding box $X \in [430, 650]$, $Y \in [390, 430]$ (100% inside safe area).
- **Stage Area & Gate S3b Fill:**
  - Ellipse semi-axes scaled to fill 92% of stage region: $R_x = 223.56$ px, $R_y = 298.08$ px, centered at $Y = 800$ px.
  - Bounding box covers $596.16$ px out of $648.0$ px stage height (**92.0% stage coverage**, comfortably exceeding Gate S3b minimum 85%).
  - Outline: 5 px wide with neon glow in PRIMARY color (`#2E6B9E`).
  - Foci: visible markers with F1 soft launch pulse and F2 expanding ring pulse at convergence.
  - Balls: at least 14 px in diameter with blue-to-orange gradient by ball index and bright fading trails.
- **Payoff Text:** Fades in during the last 4 seconds inside the caption region ($Y \approx 1250$ px, above bottom unsafe zone): `"Every ray from one focus passes through the other."` with a dark translucent backplate ensuring contrast ratio > 4.5:1.

---

## 8. Final Render Verification (Milestone P2a.1)

The ellipse billiards simulation short was rendered at final quality (1080x1920 @ 30 fps) with the unapproved default palette:
- **Output File:** `temp_renders/sim/ellipse_billiards_916_final.mp4`
- **Resolution:** 1080 x 1920 (9:16)
- **Duration:** 32.0 s (exact match with 32.0 s spec schedule)
- **Integrated Loudness:** **-14.16 LUFS** (target: $-14.0 \pm 1.0$ LUFS)
- **True Peak:** **-1.33 dBTP** (compliant with $\le -1.0$ dBTP limit)
- **LRA:** 3.10 LU
- **Sample Rate:** **48,000 Hz** stereo AAC @ 198.8 kbps (fixed from previous 96,000 Hz)
- **Spectral Centroid (first 20s):** **1782.6 Hz** (exceeds > 1.5 kHz brightness threshold)
- **Spectral Centroid (full 32s):** **2603.9 Hz**
- **Peak Sample:** 0.8578 (zero clipping, 0 consecutive full-scale runs)
- **Render Timings:**
  - Analytical Simulation: 0.005 s
  - Fast Cairo Video Render: **81.32 s** (~11.8 fps, 3x faster than previous 235.92 s)
  - Procedural Audio Build & Normalization: 10.59 s
  - FFmpeg Audio/Video Muxing: 1.14 s
  - Total Pipeline: **93.06 s** (down from 248.12 s)
- **Extracted Frames (`temp_renders/sim/frames_v2/`):**
  - Early: `frame_early_03s.png` (t = 3.0s, 3 balls fanning out)
  - Middle: `frame_middle_15s.png` (t = 15.0s, 13 balls converging)
  - Late: `frame_late_30s.png` (t = 30.0s, 55 balls with payoff text)

---

## 9. How to Add Another Simulation Short

To add a new simulation type (e.g., *Double Pendulum*, *Three-Body Problem*, *Lorenz Attractor*):

1. **Create the simulation engine:**
   Implement deterministic trajectory calculation in `core/sims/<sim_name>.py`. Provide methods to emit discrete events (bounces, transitions, extrema) and sample continuous positions at timestamp $t$.
2. **Create the simulation specification:**
   Add `sims/<sim_name>/sim_spec.json` declaring title, parameter schedules, durations, and `sound_palette` configurations.
3. **Register drawing logic in `SimulationRenderer`:**
   In `core/sims/render.py`, implement canvas rendering for the simulation's state (drawing trajectories, attractors, bodies, or phase portraits).
4. **Execute and test via the runner:**
   ```bash
   python -m pipeline.sim_run sims/<sim_name> --quality test
   python -m pipeline.sim_run sims/<sim_name> --quality final
   ```
   The runner automatically handles video rendering, procedural sound synthesis, two-pass loudness normalization, FFmpeg muxing, audio QA verification, and representative frame extraction.
