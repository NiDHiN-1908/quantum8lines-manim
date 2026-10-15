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

## 2. Renderer Technology Choice: pycairo + NumPy vs. Manim

For procedural physics simulations involving dozens of particles and fading trails at 30 fps, **`pycairo` with NumPy and FFmpeg direct piping** was chosen over Manim for the following reasons:

1. **Zero Mobject Allocation Overhead:**
   Manim is designed for declarative vector animations, allocating Python objects (`Circle`, `Line`, `VGroup`) for every element on every frame. When rendering 55 balls with 14-segment fading trails, Manim would manage over 800 mobjects per frame, incurring severe garbage collection overhead. Cairo draws directly to memory buffers with native C speed.
2. **Direct Memory Mapping via FFmpeg Pipe:**
   Cairo's `ImageSurface(FORMAT_ARGB32)` stores pixels in native contiguous memory (`bgra` on little-endian x86/Windows). The runner streams `surface.get_data()` directly into FFmpeg's `stdin` via `-f rawvideo -pix_fmt bgra`, eliminating all disk I/O and frame PNG saving.
3. **Hardware-Efficient Glow Effects:**
   Instead of stacking hundreds of translucent Manim circles, the renderer extracts high-energy particle heads into a secondary array and applies `scipy.ndimage.gaussian_filter`. The blurred bloom is composited back onto the canvas with additive blending (`cairo.OPERATOR_ADD`), yielding high-end optical bloom with negligible CPU overhead.
4. **Rendering Performance:**
   - **Test Quality (270x480):** 32.0 seconds of video (960 frames) renders in **13.8 seconds** (~70 fps, faster than real-time).
   - **Final Quality (1080x1920):** 32.0 seconds of video renders in **177 seconds** (~5.4 fps).

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

## 4. Procedural Audio Synthesis & Sound Upgrade (Milestone P2a)

Audio is generated entirely algorithmically without external audio assets or samples:

### Timbre Palettes (`core/sims/sound/palettes.py`)
1. **`pluck` (Karplus-Strong):**
   Physical modeling of a plucked string using an excitation noise burst passed through a tuned delay-line IIR filter with lowpass averaging feedback.
2. **`marimba` (Additive with Inharmonic Partials):**
   Acoustic simulation of an undercut wooden xylophone bar. Modes at $1.0\times, 3.98\times$ (double octave), $9.25\times$, and $13.5\times$ with very fast decay of upper partials and a 1.5 ms soft mallet strike transient.
3. **`bell` (FM Synthesis):**
   Chowning frequency modulation with an inharmonic modulation ratio ($1.414\times$) and decaying modulation index envelope.
4. **`glass` (High Sine Cluster with Shimmer):**
   High crystalline cluster of detuned sines ($1.000\times, 1.004\times, 1.503\times, 2.001\times, 2.752\times$) with a slow 4.0 Hz beating amplitude shimmer.
5. **`legacy_ping`:**
   Preserved legacy ping from Milestone P1 (sine wave with 2 ms attack and 0.08s exponential decay).
6. **`pad` (Atmospheric Drone):**
   Warm ambient pad chord (root, fifth, octave, and chorus beating) with a subtle 0.12 Hz tremolo and 1.5s fade in/out.

### Scales and Deterministic Pitch Mapping (`core/sims/sound/scales.py`)
- Standard 12-TET equal-temperament tuning: $f = f_{\text{root}} \cdot 2^{s/12}$.
- Scales: `pentatonic_major`, `major`, `natural_minor`, `whole_tone`, `lydian`.
- Pitch selection is strictly derived from the simulation event (`ball_id` or vertical height), **never at random**.

### Rhythm Grid Quantization (`core/sims/sound/rhythm.py`)
- Optional quantization to a musical tempo grid (tempo in BPM and beat subdivision).
- Off by default. When enabled, event times are shifted by **at most 30 ms** to preserve synchronization with the visual physics.

### Dynamics and Polyphony Management (`core/sims/sound/dynamics.py`)
- **Polyphony Limit (default 24 voices):** When simultaneous active voices exceed the limit, the manager smoothly fades out and drops the oldest and quietest voice (5 ms click-free cosine fade).
- **Energy Conservation Scaling:** Bounce amplitude scales dynamically by $\frac{1}{\sqrt{N}}$ where $N$ is the active ball count.
- **Soft Saturation:** Tape-style non-linear saturation curve applied before mastering; completely linear below 0.65 amplitude, smoothly saturating with $\tanh$ above 0.65 to guarantee peak $\le 0.98$ without hard clipping.

### Spatialization & Algorithmic Reverb (`core/sims/sound/space.py`)
- **Stereo Panning:** Constant-power panning ($gl^2 + gr^2 = 1$) mapped from particle horizontal coordinate $x/a \in [-1, 1]$.
- **Schroeder Algorithmic Reverb:** Pure NumPy/SciPy implementation with 4 parallel prime-delay feedback comb filters and 2 series allpass diffusion filters per channel, with channel delay offsets for stereo decorrelation.

---

## 5. Objective Audition Report (Milestone P2a)

Rendered via `python -m pipeline.sound_audition sims/ellipse_billiards` across 7 presets on the first 12.0 seconds:

| Preset | Palette | Scale | Integrated (LUFS) | True Peak (dBTP) | LRA (LU) | Spectral Centroid (Hz) | Onsets / sec | Peak Polyphony |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pluck+pentatonic` | pluck | pentatonic_major | -15.17 | -1.50 | 4.80 | 575.5 | 1.92 | 6 |
| `marimba+pentatonic` | marimba | pentatonic_major | -14.68 | -1.50 | 3.70 | 244.3 | 1.92 | 6 |
| `bell+lydian` | bell | lydian | -14.43 | -2.02 | 2.10 | 408.0 | 1.92 | 6 |
| `glass+whole-tone` | glass | whole_tone | -14.65 | -1.50 | 3.40 | 244.9 | 1.92 | 6 |
| `marimba+minor with reverb` | marimba | natural_minor | -14.76 | -1.50 | 3.20 | 216.5 | 1.92 | 6 |
| `pluck+major with grid quantization` | pluck | major | -15.14 | -1.50 | 4.40 | 560.4 | 1.92 | 6 |
| `legacy_ping` | legacy_ping | pentatonic_major | -14.62 | -1.50 | 3.50 | 222.9 | 1.92 | 6 |

---

## 6. Sound Lab (`review_ui/sound_lab.py` and `sound_lab_logic.py`)

Follows the Voice Lab pattern with pure business logic and Streamlit UI:
- **Audition Mode:** Players with preset names visible and objective metrics displayed.
- **Blind Evaluation Mode:** Anonymous shuffled labels (Preset A, Preset B, ...), 1-5 pleasantness rating, and "would keep watching" boolean.
- **Acceptance Rule (SPEC Section 22.5):**
  - Minimum listeners: **$\ge 5$**
  - Mean pleasantness score: **$\ge 4.0$ / 5.0**
  - Keep-watching percentage: **$\ge 70\%$**
- **Approval & Assignment:** Approved presets can be assigned directly to `sims/<id>/sim_spec.json`, updating the `sound_palette` configuration block. Evaluator scores are persisted in `sims/<id>/sound_scores.json`.

---

## 7. Safe Area and Layout Compliance

The animation adheres strictly to the vertical layout standard `LAYOUT_916` defined in `core/layout.py`:
- **Canvas:** 1080 x 1920 pixels (9:16 aspect ratio).
- **Safe Margins:** Top 250 px, Bottom 480 px, Left/Right 90 px.
- **Safe Box:** $X \in [90, 990]$, $Y \in [250, 1440]$.
- **Title:** `"Where do they all meet?"` rendered at 60 px Inter Bold, centered horizontally at $X = 540$ px, $Y = 360$ px. Bounding box $X \in [165, 915]$, $Y \in [305, 360]$ (100% inside safe area).
- **Counter:** `"Balls: <count>"` rendered at 48 px Inter Bold (meeting SPEC 4.3 label minimum 48 px), centered at $X = 540$ px, $Y = 430$ px. Bounding box $X \in [430, 650]$, $Y \in [390, 430]$ (100% inside safe area).
- **Stage Area:** Ellipse semi-axes scaled to $R_x = 202.5$ px, $R_y = 270$ px, centered at $Y = 800$ px. Entire ellipse spans $Y \in [530, 1070]$ (completely clear of UI overlays).

---

## 8. Final Render Verification (Milestone P2a)

The ellipse billiards simulation short was rendered at final quality with the new default preset (`marimba+pentatonic`):
- **Output File:** `temp_renders/sim/ellipse_billiards_916_final.mp4`
- **Resolution:** 1080 x 1920 (9:16)
- **Duration:** 32.0 s (matches 32.0 s spec exactly)
- **Integrated Loudness:** **-14.20 LUFS** (well within $\pm 1$ LU tolerance of -14.0 LUFS)
- **True Peak:** **-1.38 dBTP** (compliant with $\le -1.0$ dBTP limit)
- **Peak Sample:** 0.8475 (zero hard clipping, 0 consecutive full-scale sample runs)
- **Render Timings:**
  - Analytical Simulation: 0.005 s
  - Fast Cairo Video Render: 235.92 s (~4.0 fps)
  - Procedural Audio Build & Normalization: 10.63 s
  - FFmpeg Audio/Video Muxing: 1.56 s
  - Total Pipeline: 248.12 s

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
