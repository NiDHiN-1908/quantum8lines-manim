"""
Font management for Quantum8Lines animations.
Provides static Inter font validation and registration for Manim Text typography.
Follows SPEC.md Section 4 and Milestone M3b Step 0.
"""

from pathlib import Path
import manimpango

INTER_FONT_NAME = "Inter"
NOTO_DEVANAGARI_FONT_NAME = "Noto Sans Devanagari"

FONTS_DIR = Path(__file__).resolve().parents[1] / "brand" / "fonts"
INTER_REGULAR_PATH = FONTS_DIR / "Inter-Regular.ttf"
INTER_SEMIBOLD_PATH = FONTS_DIR / "Inter-SemiBold.ttf"
INTER_BOLD_PATH = FONTS_DIR / "Inter-Bold.ttf"
NOTO_DEVANAGARI_PATH = FONTS_DIR / "NotoSansDevanagari.ttf"


def is_font_available(font_name: str) -> bool:
    """Check if a font family is available in ManimPango/Fontconfig."""
    available = [f.lower() for f in manimpango.list_fonts()]
    return any(font_name.lower() in f for f in available)


def register_project_fonts() -> bool:
    """
    Attempt to register static local font files from brand/fonts/ into ManimPango.
    Returns True if Inter static fonts are successfully registered.
    """
    registered = False
    for font_path in [INTER_REGULAR_PATH, INTER_SEMIBOLD_PATH, INTER_BOLD_PATH]:
        if font_path.exists():
            res = manimpango.register_font(str(font_path))
            if res:
                registered = True

    if NOTO_DEVANAGARI_PATH.exists():
        manimpango.register_font(str(NOTO_DEVANAGARI_PATH))

    return registered


def get_inter_font() -> str:
    """
    Returns the Inter font family name for use in Manim Text mobjects.
    Raises RuntimeError with Windows installation instructions if not available.
    """
    if not is_font_available(INTER_FONT_NAME):
        register_project_fonts()

    if not is_font_available(INTER_FONT_NAME):
        raise RuntimeError(
            "Font 'Inter' is not installed or registered on this system.\n"
            "To install Inter on Windows:\n"
            "  1. Open 'brand/fonts/Inter-Regular.ttf' and 'Inter-Bold.ttf' in File Explorer.\n"
            "  2. Click 'Install' or 'Install for all users'.\n"
            "  3. Alternatively, copy Inter-*.ttf to %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts."
        )

    return INTER_FONT_NAME
