# Quantum8Lines Layout Engine Specifications (M1)

This document specifies the exact coordinate bounds, safe zones, and content regions for 16:9 and 9:16 canvases per **SPEC.md Section 4.3**.

## Coordinate Space & Scaling
Manim places origin $(0, 0, 0)$ at the center of the viewport.
Both layouts use an identical isotropic coordinate scale:
$$\text{px per unit} = \frac{\text{pixel height}}{\text{frame height}} = \frac{1080}{8.0} = \frac{1920}{14.2222} = 135\text{ px/unit}$$

- **Pixels to units:** $\text{units} = \frac{\text{px}}{135}$
- **Units to pixels:** $\text{px} = \text{units} \times 135$

---

## 1. 16:9 Landscape (`LAYOUT_169`)

- **Canvas Pixels:** $1920 \times 1080$ px at 30 fps
- **Manim Frame:** Width $14.222$, Height $8.0$
- **Total Coordinates:** $x \in [-7.111, +7.111]$, $y \in [-4.0, +4.0]$
- **Safe Zone (5% Title-Safe Margin):**
  - Margins: Left/Right $96$ px ($0.711$ units), Top/Bottom $54$ px ($0.400$ units)
  - Safe Coordinates: $x \in [-6.400, +6.400]$, $y \in [-3.600, +3.600]$
  - Safe Area Dimensions: $12.800 \times 7.200$ units ($1728 \times 972$ px)

### 16:9 Regions (Manim Units)

| Region | Center $(x, y)$ | Dimensions $(W \times H)$ | $X$ Extents | $Y$ Extents | Purpose |
|---|---|---|---|---|---|
| **title** | $(0.0, 3.0)$ | $12.0 \times 1.0$ | $[-6.0, +6.0]$ | $[+2.5, +3.5]$ | Episode title, topic context |
| **stage** | $(0.0, 0.4)$ | $12.0 \times 4.0$ | $[-6.0, +6.0]$ | $[-1.6, +2.4]$ | Mathematical objects, vectors, equations |
| **caption** | $(0.0, -2.3)$ | $11.0 \times 1.2$ | $[-5.5, +5.5]$ | $[-2.9, -1.7]$ | Subtitles / karaoke spoken word highlight |
| **footer** | $(0.0, -3.25)$| $11.0 \times 0.6$ | $[-5.5, +5.5]$ | $[-3.55, -2.95]$ | Secondary cues, chapter progress |

---

## 2. 9:16 Portrait (`LAYOUT_916`)

- **Canvas Pixels:** $1080 \times 1920$ px at 30 fps
- **Manim Frame:** Width $8.0$, Height $14.222$
- **Total Coordinates:** $x \in [-4.0, +4.0]$, $y \in [-7.111, +7.111]$
- **Safe Zone (Reels/Shorts UI Clearance):**
  - Top Margin: $250$ px ($1.852$ units) — clear story/app header
  - Bottom Margin: $480$ px ($3.556$ units) — clear captions, sound disc, profile UI
  - Left/Right Margins: $90$ px ($0.667$ units) — clear edge gestures and share buttons
  - Safe Coordinates: $x \in [-3.333, +3.333]$, $y \in [-3.555, +5.259]$
  - Safe Center: $(0.0, +0.852)$
  - Safe Area Dimensions: $6.667 \times 8.815$ units ($900 \times 1190$ px)

### 9:16 Regions (Manim Units)

| Region | Center $(x, y)$ | Dimensions $(W \times H)$ | $X$ Extents | $Y$ Extents | Purpose |
|---|---|---|---|---|---|
| **title** | $(0.0, 4.4)$ | $6.4 \times 1.4$ | $[-3.2, +3.2]$ | $[+3.7, +5.1]$ | Hook title / question |
| **stage** | $(0.0, 1.2)$ | $6.4 \times 4.8$ | $[-3.2, +3.2]$ | $[-1.2, +3.6]$ | Primary animation stage |
| **caption** | $(0.0, -2.1)$ | $6.2 \times 1.6$ | $[-3.1, +3.1]$ | $[-2.9, -1.3]$ | Animated captions (sits above bottom zone) |
| **footer** | $(0.0, -3.2)$ | $6.2 \times 0.6$ | $[-3.1, +3.1]$ | $[-3.5, -2.9]$ | Call-to-action / swipe indicator |
