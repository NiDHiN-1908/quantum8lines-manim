# Quantum8Lines Mascot Specification

Follows **SPEC.md Section 4.5** and **Milestone M2 Step 3**.

---

## 1. Character Identity & Visual Design

The channel mascot is derived from the official Quantum8Lines brain icon asset (`brand/brain_icon.svg`):
- **Base Geometry**: Symmetrical dual-hemisphere brain icon. The left hemisphere embodies dynamic transformation (`DYNAMIC` / `#00a2e8`), and the right hemisphere embodies energetic curiosity (`HIGHLIGHT` / `#ff7f27`).
- **Facial Features**: Two simple, minimalist circular eyes placed symmetrically over the brain hemispheres. Each eye consists of a clean white sclera (`TEXT` / `WHITE`) and a dark centered pupil (`BACKGROUND` / `#0e0e11`).
- **Design Philosophy**: Minimalist and modern. Avoids unnecessary anthropomorphic clutter (no mouths, arms, or accessories). Expressiveness comes purely through subtle posture, gaze, and eye state transformations.

---

## 2. On-Screen Rules & Positioning

Per SPEC Section 4.5:
1. **Never Covers the Stage**: The mascot is strictly positioned in corner areas outside the central `stage` region.
2. **Safe Zone Compliance**: When placed using `.place_corner(layout, corner)`, the mascot lies entirely inside the layout's safe area boundaries:
   - **16:9 Landscape**: Sits in corners (e.g., bottom-right at $(5.0, -2.5)$) well clear of stage bounds ($y \in [-1.6, 2.4]$).
   - **9:16 Portrait**: Sits in corner areas (e.g., bottom-right at $(2.3, -2.7)$) above the bottom UI dead-zone and outside the vertical stage region ($y \in [-1.2, 3.6]$).
3. **Appearance Frequency**: Appears at most 3 times per short chapter to maintain focus on the mathematical narrative. It never carries essential mathematical information.

---

## 3. Expressive States & Animations

The `Mascot` class exposes five state methods, each returning a composable Manim animation:

| State | Method | Animation Mechanics | Psychological Role |
|---|---|---|---|
| **`idle`** | `mascot.idle()` | Gentle vertical bobbing (`0.12 * UP`) with `rate_functions.wiggle` | Living, breathing presence during pauses |
| **`blink`** | `mascot.blink()` | Vertical eye scaling (`[1.0, 0.1, 1.0]`) via `rate_functions.there_and_back` | Natural biological micro-animation |
| **`think`** | `mascot.think()` | Inquisitive head tilt ($14^\circ$) around base anchor | Pondering a question before an explanation |
| **`surprised`**| `mascot.surprised()` | Simultaneous 1.1x scale pop and 1.3x eye widening | Aha moments, unexpected mathematical twists |
| **`point`** | `mascot.point(target)`| Dynamic orientation tilt directed toward a target object | Directing viewer attention to a key equation or vector |

---

## 4. Usage Example

```python
from manim import Scene
from core.components import Mascot
from core.layout import LAYOUT_169

class MascotDemoScene(Scene):
    def construct(self):
        mascot = Mascot()
        mascot.place_corner(LAYOUT_169, "bottom_right")
        self.add(mascot)

        # Mascot reactions during narration
        self.play(mascot.blink())
        self.play(mascot.think())
        self.play(mascot.surprised())
```
