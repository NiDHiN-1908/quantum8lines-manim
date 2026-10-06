# Quantum8Lines Design Tokens

This document defines the semantic color system used across all Quantum8Lines animations and layouts.

## Principle: Semantic Consistency
Colors must **never be randomized or used purely for decorative variation**. Every color has an invariant semantic meaning across the channel so viewers build visual intuition without cognitive friction:

| Token | Value / Manim Color | Semantic Meaning | Usage Examples |
|---|---|---|---|
| `BACKGROUND` | `#0e0e11` | Infinite space canvas | Canvas background for all 16:9 and 9:16 scenes. |
| `PRIMARY` | `BLUE` (`#58C4DD`) | Primary entity / existence | The core object being studied (e.g. the eigenvector, base function $f(x)$). |
| `SECONDARY` | `YELLOW` (`#FFFF00`) | Emergence / result | Computed outcomes, transformed states, solutions ($x = \pm 2$). |
| `DYNAMIC` | `RED` (`#FC6255`) | Change / motion / force | Vectors in active motion, shear transformations, derivative slopes. |
| `STATIC` | `GREY_B` (`#BBBBBB`) | Inactive / reference frame | Invariant axes, background vector fields, grid lines, structural operators. |
| `HIGHLIGHT` | `GREEN` (`#83C167`) | Focus / attention / cue | The spoken word in karaoke captions, key term emphasis, visual callouts. |
| `TEXT` | `WHITE` (`#FFFFFF`) | Primary typography | Labels, equation characters, non-highlighted subtitles. |

## Rules
1. **No Raw Colors in Scenes:** Raw Manim color constants (`BLUE`, `YELLOW`, `WHITE`, etc.) are forbidden in scene code; all components and scenes import from `core.tokens`.
2. **Persistence Across Topics:** A color role never flips its meaning between chapters or topics.
