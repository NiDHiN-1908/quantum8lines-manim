from manim import *
import json
import os
import random
import numpy as np
from manim.utils.rate_functions import ease_out_sine, ease_out_quad, ease_out_cubic, ease_in_cubic, ease_in_sine

# Load brand colors
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "brand.json")
try:
    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)
    colors = config_data["colors"]
except Exception:
    # Safe fallback if config file is not readable or missing
    colors = {
        "blue_dark": "#0a4b7c",
        "blue_light": "#1e88e5",
        "orange_dark": "#8c3b00",
        "orange_light": "#f57c00",
        "gold": "#ffb000",
        "white_badge": "#ffffff",
        "background": "#141518"
    }

class Quantum8LinesIntro(Scene):
    # 0 = Combined (full 10s run), 1-4 = Specific Phase (for separate review)
    phase_to_run = 0

    def create_elements(self):
        """
        Creates all logo components and saves them in a dictionary.
        Uses exact mathematical parameters to split the "8" outline left/right
        and avoid vertical cutlines.
        """
        # Outer dimensions
        r1 = 1.45  # Radius of top loop
        r2 = 1.85  # Radius of bottom loop
        d = 1.7    # Distance between centers (UP*0.85 to DOWN*0.85)

        # 1. Solve intersection of circles centered at (0, d/2) and (0, -d/2)
        y_i = (r2**2 - r1**2) / (2 * d)
        x_i = np.sqrt(max(0.0, r1**2 - (y_i - d/2)**2))

        # Arc angles for top circle (centered at UP * 0.85)
        theta_left = np.arctan2(y_i - d/2, -x_i)
        if theta_left < 0: theta_left += 2 * np.pi
        theta_right_raw = np.arctan2(y_i - d/2, x_i)

        # Arc angles for bottom circle (centered at DOWN * 0.85)
        phi_left = np.arctan2(y_i + d/2, -x_i)
        if phi_left < 0: phi_left += 2 * np.pi
        phi_right_raw = np.arctan2(y_i + d/2, x_i)

        # Left Outer boundary arcs
        top_left_arc = Arc(
            radius=r1,
            start_angle=90 * DEGREES,
            angle=theta_left - 90 * DEGREES
        ).shift(UP * 0.85)

        bottom_left_arc = Arc(
            radius=r2,
            start_angle=phi_left,
            angle=270 * DEGREES - phi_left
        ).shift(DOWN * 0.85)

        left_outline = VGroup(top_left_arc, bottom_left_arc)

        # Right Outer boundary arcs
        top_right_arc = Arc(
            radius=r1,
            start_angle=90 * DEGREES,
            angle=theta_right_raw - 90 * DEGREES
        ).shift(UP * 0.85)

        bottom_right_arc = Arc(
            radius=r2,
            start_angle=phi_right_raw,
            angle=-90 * DEGREES - phi_right_raw
        ).shift(DOWN * 0.85)

        right_outline = VGroup(top_right_arc, bottom_right_arc)

        # Apply neon glow layered stroke trick
        def get_glow_layers(outline_vg, color):
            glow1 = outline_vg.copy().set_stroke(color=color, width=11, opacity=0.18)
            glow2 = outline_vg.copy().set_stroke(color=color, width=6, opacity=0.38)
            crisp = outline_vg.copy().set_stroke(color=color, width=2.2, opacity=1.0)
            return VGroup(glow1, glow2, crisp)

        left_neon = get_glow_layers(left_outline, colors["blue_light"])
        right_neon = get_glow_layers(right_outline, colors["orange_light"])

        # 2. Inside Gradient Fill + Starfield (Phase 2 MVP)
        outer_top = Circle(radius=r1).shift(UP * 0.85)
        outer_bottom = Circle(radius=r2).shift(DOWN * 0.85)
        eight_fill = Union(outer_top, outer_bottom)
        eight_fill.set_fill(
            color=[colors["blue_light"], colors["orange_light"]],
            opacity=0.75
        )
        eight_fill.set_stroke(width=0)

        # Scatter stars inside the figure-8 shape boundary
        random.seed(1337)
        stars = VGroup()
        star_count = 0
        while star_count < 25:
            xs = random.uniform(-1.85, 1.85)
            ys = random.uniform(-2.7, 2.3)
            # Math check: is the point inside the top or bottom circle boundary?
            in_top = xs**2 + (ys - 0.85)**2 <= r1**2
            in_bottom = xs**2 + (ys + 0.85)**2 <= r2**2
            if in_top or in_bottom:
                star = Dot(
                    point=[xs, ys, 0],
                    radius=random.uniform(0.015, 0.045),
                    color=WHITE,
                    fill_opacity=random.uniform(0.4, 0.95)
                )
                stars.add(star)
                star_count += 1

        # 3. Orbiting rings (Atom-orbit style)
        ring1 = Ellipse(width=4.3, height=1.55).rotate(0 * DEGREES)
        ring2 = Ellipse(width=4.3, height=1.55).rotate(60 * DEGREES)
        ring3 = Ellipse(width=4.3, height=1.55).rotate(120 * DEGREES)
        
        ring1.set_stroke(color=colors["blue_light"], width=2.0, opacity=0.7)
        ring2.set_stroke(color=colors["blue_light"], width=2.0, opacity=0.7)
        ring3.set_stroke(color=colors["gold"], width=2.0, opacity=0.7)
        orbits = VGroup(ring1, ring2, ring3)

        # Staggered orbiting particles (with glow)
        particles = VGroup()
        ring_refs = [ring1, ring1, ring2, ring2, ring3, ring3]
        particle_speeds = [0.15, 0.15, 0.18, 0.18, 0.13, 0.13]
        particle_phases = [0.0, 0.5, 0.25, 0.75, 0.1, 0.6]
        particle_colors = [
            colors["blue_light"], colors["blue_light"],
            colors["blue_light"], colors["blue_light"],
            colors["gold"], colors["gold"]
        ]

        for idx, ring in enumerate(ring_refs):
            glow_p = VGroup(
                Dot(color=particle_colors[idx], radius=0.14, fill_opacity=0.35),
                Dot(color=WHITE, radius=0.04, fill_opacity=1.0)
            )
            particles.add(glow_p)

        # 4. Final Settle State Gradient "8" Shape
        final_8 = Union(outer_top, outer_bottom)
        final_8.set_fill(
            color=[colors["blue_light"], colors["orange_light"]],
            opacity=0.65
        )
        final_8.set_stroke(width=0)

        # 5. Brain SVG
        svg_path = os.path.join(os.path.dirname(__file__), "brain_icon.svg")
        try:
            brain = SVGMobject(svg_path)
            brain.scale_to_fit_height(1.35)
            brain.move_to(ORIGIN)
            if len(brain) >= 2:
                brain[0].set_fill(colors["blue_light"], opacity=1.0)
                brain[1].set_fill(colors["orange_light"], opacity=1.0)
                brain[0].set_stroke(color=WHITE, width=1.2, opacity=1.0)
                brain[1].set_stroke(color=WHITE, width=1.2, opacity=1.0)
            else:
                brain.set_fill(WHITE, opacity=1.0)
                brain.set_stroke(color=WHITE, width=1.2, opacity=1.0)
        except Exception:
            left_hem = Circle(radius=0.45, color=colors["blue_light"]).shift(LEFT * 0.22)
            right_hem = Circle(radius=0.45, color=colors["orange_light"]).shift(RIGHT * 0.22)
            brain = VGroup(left_hem, right_hem).scale(0.85).move_to(ORIGIN)

        # 6. Dissolve/pixelate cluster of squares
        squares = VGroup()
        for _ in range(40):
            size = random.uniform(0.08, 0.22)
            x_factor = random.random() ** 1.6
            x = 1.65 + x_factor * 2.8
            y = random.uniform(-1.5, 1.5)

            if random.random() < 0.7:
                color = random.choice([colors["orange_light"], colors["orange_dark"], colors["gold"]])
            else:
                color = random.choice([colors["blue_light"], colors["blue_dark"]])

            sq = Square(side_length=size)
            sq.set_fill(color, opacity=random.uniform(0.55, 0.95))
            sq.set_stroke(width=0)
            sq.move_to(np.array([x, y, 0]))

            sq.target_pos = sq.get_center()
            squares.add(sq)

        # 7. Wordmark text
        text = Text("QUANTUM 8 LINES", font="Arial", font_size=34, weight="BOLD")
        text.next_to(outer_bottom, DOWN, buff=0.7)
        for i, char in enumerate(text):
            if i == 8:  # The "8" character index
                char.set_color(colors["orange_light"])
            else:
                char.set_color(WHITE)

        return {
            "left_neon": left_neon,
            "right_neon": right_neon,
            "eight_fill": eight_fill,
            "stars": stars,
            "orbits": orbits,
            "ring1": ring1,
            "ring2": ring2,
            "ring3": ring3,
            "particles": particles,
            "ring_refs": ring_refs,
            "particle_speeds": particle_speeds,
            "particle_phases": particle_phases,
            "final_8": final_8,
            "brain": brain,
            "squares": squares,
            "text": text
        }

    def start_updaters(self, comps):
        """Adds rotational and parametric updaters to orbits and particles."""
        if not hasattr(comps["ring1"], "has_updater_active"):
            comps["ring1"].has_updater_active = True
            comps["ring1"].add_updater(lambda m, dt: m.rotate(0.08 * dt))
            comps["ring2"].add_updater(lambda m, dt: m.rotate(0.12 * dt))
            comps["ring3"].add_updater(lambda m, dt: m.rotate(-0.10 * dt))

        for idx, pt in enumerate(comps["particles"]):
            if not hasattr(pt, "has_updater_active"):
                pt.has_updater_active = True
                ring = comps["ring_refs"][idx]
                speed = comps["particle_speeds"][idx]
                phase = comps["particle_phases"][idx]

                def make_updater(r, s, p):
                    def updater_func(m, dt):
                        m.time_elapsed += dt
                        t = (m.time_elapsed * s + p) % 1.0
                        m.move_to(r.point_from_proportion(t))
                    return updater_func

                pt.time_elapsed = 0.0
                pt.add_updater(make_updater(ring, speed, phase))

    def construct(self):
        # Setup background color
        self.camera.background_color = colors["background"]

        # Build elements
        comps = self.create_elements()

        if self.phase_to_run == 1:
            self.play_phase_1(comps)
        elif self.phase_to_run == 2:
            self.setup_phase_2(comps)
            self.play_phase_2(comps)
        elif self.phase_to_run == 3:
            self.setup_phase_3(comps)
            self.play_phase_3(comps)
        elif self.phase_to_run == 4:
            self.setup_phase_4(comps)
            self.play_phase_4(comps)
        else:
            # Combined full 10-second run
            self.play_phase_1(comps)
            self.play_phase_2(comps)
            self.play_phase_3(comps)
            self.play_phase_4(comps)

    # --- Phase Play & Setup Functions ---

    def play_phase_1(self, comps):
        """PHASE 1 (0.0s - 1.5s): Brain reveal & hold"""
        brain = comps["brain"]
        self.add(brain)
        self.play(DrawBorderThenFill(brain, run_time=1.0))
        self.wait(0.5)

    def setup_phase_2(self, comps):
        """Immediately adds Phase 1 complete state"""
        self.add(comps["brain"])

    def play_phase_2(self, comps):
        """PHASE 2 (1.5s - 4.5s): Neon "8" outline draws, then fills"""
        left_neon = comps["left_neon"]
        right_neon = comps["right_neon"]
        eight_fill = comps["eight_fill"]
        stars = comps["stars"]
        brain = comps["brain"]

        eight_fill.set_opacity(0)
        stars.set_opacity(0)
        
        self.add(left_neon, right_neon, eight_fill, stars)
        # Keep brain on top
        self.bring_to_front(brain)

        # 1. Traced neon drawing (2.0s)
        self.play(
            Create(left_neon, run_time=2.0, rate_func=ease_out_sine),
            Create(right_neon, run_time=2.0, rate_func=ease_out_sine),
        )
        # 2. Fade in gradient galaxy fill + stars (1.0s)
        self.play(
            eight_fill.animate.set_opacity(0.75),
            stars.animate.set_opacity(1.0),
            run_time=1.0,
            rate_func=ease_out_quad
        )

    def setup_phase_3(self, comps):
        """Immediately adds Phase 2 complete state"""
        self.add(comps["brain"])
        self.add(comps["left_neon"], comps["right_neon"])
        self.add(comps["eight_fill"], comps["stars"])
        self.bring_to_front(comps["brain"])
        self.bring_to_front(comps["left_neon"])
        self.bring_to_front(comps["right_neon"])

    def play_phase_3(self, comps):
        """PHASE 3 (4.5s - 7.5s): Fill fades out, orbits appear"""
        eight_fill = comps["eight_fill"]
        stars = comps["stars"]
        orbits = comps["orbits"]
        particles = comps["particles"]
        brain = comps["brain"]
        left_neon = comps["left_neon"]
        right_neon = comps["right_neon"]

        particles.set_opacity(0)
        self.add(orbits, particles)
        
        # Draw rings, fade in particles, and remove galaxy fill/stars
        self.play(
            FadeOut(eight_fill, run_time=1.0),
            FadeOut(stars, run_time=1.0),
            Create(orbits, run_time=1.2, rate_func=ease_out_sine),
            FadeIn(particles, run_time=1.0),
        )

        # Trigger updaters to start rotation & motion
        self.start_updaters(comps)

        # Bring layers to front
        self.bring_to_front(brain)
        self.bring_to_front(left_neon)
        self.bring_to_front(right_neon)
        self.bring_to_front(particles)

        # Hold for remainder of phase
        self.wait(1.8)

    def setup_phase_4(self, comps):
        """Immediately adds Phase 3 complete state and starts updaters"""
        self.add(comps["brain"])
        self.add(comps["left_neon"], comps["right_neon"])
        self.add(comps["orbits"])
        self.add(comps["particles"])
        self.start_updaters(comps)
        
        self.bring_to_front(comps["brain"])
        self.bring_to_front(comps["left_neon"])
        self.bring_to_front(comps["right_neon"])
        self.bring_to_front(comps["particles"])

    def play_phase_4(self, comps):
        """PHASE 4 (7.5s - 10.0s): Settle to final logo state"""
        left_neon = comps["left_neon"]
        right_neon = comps["right_neon"]
        final_8 = comps["final_8"]
        squares = comps["squares"]
        text = comps["text"]
        brain = comps["brain"]
        orbits = comps["orbits"]
        particles = comps["particles"]

        final_8.set_opacity(0)
        self.add(final_8)

        # Prepare squares for scale-in
        for sq in squares:
            sq.save_state()
            sq.scale(0.1)
            sq.set_opacity(0)
        self.add(squares)

        # Settle transition
        self.play(
            # Fade out neon neon glows
            FadeOut(left_neon, run_time=1.0),
            FadeOut(right_neon, run_time=1.0),
            # Fade in final semi-transparent solid gradient "8"
            FadeIn(final_8, run_time=1.0),
            # Scale and fade in pixel squares
            LaggedStart(*[Restore(sq) for sq in squares], lag_ratio=0.02, run_time=1.2),
            # Fade in wordmark
            FadeIn(text, shift=UP * 0.25, run_time=1.0),
        )

        # Layers arrangement (send final_8 to the back manually)
        if final_8 in self.mobjects:
            self.mobjects.remove(final_8)
            self.mobjects.insert(0, final_8)

        self.bring_to_front(brain)
        self.bring_to_front(orbits)
        self.bring_to_front(particles)

        # Hold final frame
        self.wait(1.3)

# --- Subclasses for Independent Testing of Each Phase ---

class Quantum8LinesIntroPhase1(Quantum8LinesIntro):
    phase_to_run = 1

class Quantum8LinesIntroPhase2(Quantum8LinesIntro):
    phase_to_run = 2

class Quantum8LinesIntroPhase3(Quantum8LinesIntro):
    phase_to_run = 3

class Quantum8LinesIntroPhase4(Quantum8LinesIntro):
    phase_to_run = 4

# --- Outro Scene ---

class Quantum8LinesOutro(Scene):
    def construct(self):
        self.camera.background_color = colors["background"]
        intro_inst = Quantum8LinesIntro()
        comps = intro_inst.create_elements()

        # Add all finished elements
        self.add(comps["final_8"], comps["brain"], comps["orbits"], comps["particles"], comps["squares"], comps["text"])
        intro_inst.start_updaters(comps)

        self.wait(1.0)

        # Dissolve squares
        squares_sorted = sorted(comps["squares"], key=lambda s: s.get_center()[0])
        self.play(
            LaggedStart(
                *[sq.animate.move_to(sq.get_center() + sq.target_pos * 0.5).scale(0.2).set_opacity(0) 
                  for sq in squares_sorted],
                lag_ratio=0.03,
                run_time=1.2
            )
        )

        # Clear updaters before final fade
        comps["ring1"].clear_updaters()
        comps["ring2"].clear_updaters()
        comps["ring3"].clear_updaters()
        for p in comps["particles"]:
            p.clear_updaters()

        # Fade out
        self.play(
            comps["final_8"].animate.scale(0.7).set_opacity(0),
            comps["brain"].animate.scale(0.7).set_opacity(0),
            comps["orbits"].animate.scale(1.2).set_opacity(0),
            comps["particles"].animate.scale(1.2).set_opacity(0),
            comps["text"].animate.shift(DOWN * 0.2).set_opacity(0),
            run_time=1.2,
            rate_func=ease_out_sine
        )
        self.wait(0.5)
