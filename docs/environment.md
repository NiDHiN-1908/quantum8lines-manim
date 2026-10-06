# Environment & Benchmark (Milestone M0)

## 1. Hardware Specifications

- **Operating System:** Microsoft Windows 11 Home Single Language (64-bit)
- **CPU:** 13th Gen Intel(R) Core(TM) i7-13620H (10 cores [6 Performance + 4 Efficient], 16 threads)
- **RAM:** 16 GB DDR5 (15.64 GB usable)
- **GPU (Discrete):** NVIDIA GeForce RTX 4050 Laptop GPU (6 GB GDDR6)
- **GPU (Integrated):** Intel(R) UHD Graphics

---

## 2. Tool & Engine Versions

| Tool / Dependency | Version | Location / Source |
|---|---|---|
| **Python** | `3.11.9` | C:\Users\nidhi\AppData\Local\Programs\Python\Python311 |
| **uv** | `0.11.32` | System PATH |
| **Manim Community** | `0.21.0` | uv managed environment |
| **FFmpeg** | `8.0.1-essentials` | System PATH |
| **FFprobe** | `8.0.1-essentials` | System PATH |
| **LaTeX (pdfTeX)** | `MiKTeX 25.12 (pdfTeX 4.23)` | System PATH |
| **dvisvgm** | `3.4.3` | System PATH |
| **NumPy** | `2.4.6` | uv managed environment |
| **SymPy** | `1.14.0` | uv managed environment |
| **Pydantic** | `2.13.5` | uv managed environment |
| **Pytest** | `9.1.1` | uv managed environment |
| **Kokoro-ONNX** | `0.6.1` | uv managed environment |
| **Faster-Whisper** | `1.2.1` | uv managed environment |
| **SoundFile** | `0.14.0` | uv managed environment |
| **Streamlit** | `1.65.0` | uv managed environment |

---

## 3. Render Benchmarks (`HelloScene`)

Render benchmark performed on `core/scene_base.py` (`HelloScene`: arrow vector creation + LaTeX label $\vec{v}$ fade-in, 2.1 seconds duration at 30 fps).

| Format | Resolution | Manim Frame Dimensions | Frame Rate | Render Time | File Size | Output Path |
|---|---|---|---|---|---|---|
| **16:9** (Landscape) | 1920 x 1080 | Width 14.222, Height 8.0 | 30 fps | **2.56 s** | 36.8 KB | `temp_renders/16_9/hello_16x9.mp4` |
| **9:16** (Portrait) | 1080 x 1920 | Width 8.0, Height 14.222 | 30 fps | **2.25 s** | 37.0 KB | `temp_renders/9_16/hello_9x16.mp4` |

Both formats verified using `ffprobe` for pixel dimensions and frame rate compliance with SPEC.md section 4.3.
