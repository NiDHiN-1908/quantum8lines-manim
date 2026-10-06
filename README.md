# Quantum8Lines Manim Videos

This repository contains Manim scenes and animations for Quantum8Lines.

## Brand Assets & Sting Animations

We have built a beautiful brand sting animation (intro/outro) using native Manim shapes. The assets and colors are configured to be modular and reusable.

### Configuration
- Brand colors are configured in [config/brand.json](file:///c:/Users/nidhi/Desktop/quantum8lines-manim/config/brand.json).
- The vector asset for the brain is located at [assets/brand/brain_icon.svg](file:///c:/Users/nidhi/Desktop/quantum8lines-manim/assets/brand/brain_icon.svg).

### Rendering Scenes

To render the brand intro and outro animations, run the following commands from the root directory of the workspace using the project's virtual environment:

#### Draft Quality (Quick render, 480p, 15fps)
```bash
.venv/Scripts/manim -ql assets/brand/intro_outro.py Quantum8LinesIntro
.venv/Scripts/manim -ql assets/brand/intro_outro.py Quantum8LinesOutro
```

#### Medium Quality (720p, 30fps)
```bash
.venv/Scripts/manim -qm assets/brand/intro_outro.py Quantum8LinesIntro
.venv/Scripts/manim -qm assets/brand/intro_outro.py Quantum8LinesOutro
```

#### High Quality (1080p, 60fps)
```bash
.venv/Scripts/manim -qh assets/brand/intro_outro.py Quantum8LinesIntro
.venv/Scripts/manim -qh assets/brand/intro_outro.py Quantum8LinesOutro
```

#### Production Quality (4K, 60fps)
```bash
.venv/Scripts/manim -qk assets/brand/intro_outro.py Quantum8LinesIntro
.venv/Scripts/manim -qk assets/brand/intro_outro.py Quantum8LinesOutro
```

The rendered outputs will be placed in the `media/videos/intro_outro` directory.
