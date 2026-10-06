"""
Design tokens for Quantum8Lines animations.
Semantic color roles preserving legacy meanings and brand values.
Rule: Raw Manim color names may appear ONLY in this file.
"""

from manim import BLUE, YELLOW, RED, GREY_B, GREEN, WHITE

# Canvas Background
BACKGROUND = "#0e0e11"

# Semantic Color Roles
PRIMARY = BLUE        # Main mathematical object / primary existence
SECONDARY = YELLOW    # Emergence / result / derived mathematical entity
DYNAMIC = RED         # Change, motion, transformation, applied force
STATIC = GREY_B       # Reference frame, inactive geometry, grid context
HIGHLIGHT = GREEN     # Active focus, attention cue, karaoke caption highlight
TEXT = WHITE          # Default text, labels, equation typography
