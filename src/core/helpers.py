from manim import *

def pause(scene, duration=0.5):
    scene.wait(duration)

def smooth_shift(mobject, direction, distance, run_time=2, rate_func=smooth):
    return mobject.animate.shift(direction * distance).set_run_time(run_time).set_rate_func(rate_func)

def traced(mobject, color, width=4):
    return TracedPath(
        mobject.get_center,
        stroke_color=color,
        stroke_width=width,
        dissipating_time=0
    )
