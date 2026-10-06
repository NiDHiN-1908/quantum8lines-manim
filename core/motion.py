"""
Motion language and animation timing constants for Quantum8Lines.
Follows SPEC.md Section 4.4:
  - Default animation duration 0.6-1.0 s
  - Transitions between ideas 0.4-0.6 s
  - Easing: smooth unless a rule says otherwise
  - At most one thing moves at a time
"""

from manim import rate_functions

# Core durations (in seconds)
DEFAULT_RUN_TIME = 0.8        # Standard animations (0.6 - 1.0 s)
MIN_RUN_TIME = 0.6
MAX_RUN_TIME = 1.0

TRANSITION_DURATION = 0.5     # Between ideas / scenes (0.4 - 0.6 s)
TRANSITION_RUN_TIME = 0.5
FAST_RUN_TIME = 0.4

PULSE_DURATION = 0.6          # Highlighting or pulsing elements
REVEAL_DURATION = 0.8         # Introducing new elements

# Default easing
DEFAULT_EASING = rate_functions.smooth
SMOOTH = rate_functions.smooth
LINEAR = rate_functions.linear
EASE_OUT = rate_functions.ease_out_cubic
EASE_IN_OUT = rate_functions.ease_in_out_cubic
