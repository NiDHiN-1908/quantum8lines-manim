"""
Quantum8Lines Sound Lab - Streamlit Review UI
Run with: uv run streamlit run review_ui/sound_lab.py
Follows SPEC.md Section 22.5 and Milestone P2a Step 3.
"""

from pathlib import Path
import json
import random
import streamlit as st

from review_ui.sound_lab_logic import (
    ACCEPTANCE_RULES,
    DEFAULT_SCORES_PATH,
    DEFAULT_SIM_DIR,
    aggregate_sound_scores,
    approve_preset,
    assign_palette_to_sim,
    load_sound_scores,
    record_sound_evaluation,
)
from pipeline.sound_audition import AUDITION_PRESETS, run_sound_audition


st.set_page_config(
    page_title="Quantum8Lines Sound Lab",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 Quantum8Lines Sound Lab")
st.caption("Procedural simulation sound audition, blind evaluation, acceptance testing, approval, and sim assignment.")


# ---------------------------------------------------------------------------
# Navigation Tabs
# ---------------------------------------------------------------------------
tab_audition, tab_blind, tab_results, tab_approve, tab_assign = st.tabs([
    "1. Audition",
    "2. Blind Test",
    "3. Results & Acceptance",
    "4. Approve Preset",
    "5. Assign to Simulation",
])


# ---------------------------------------------------------------------------
# Tab 1: Audition
# ---------------------------------------------------------------------------
with tab_audition:
    st.header("Procedural Sound Presets Audition")
    st.markdown(
        "Listen to candidate sound palettes and spatial treatments on the simulation short (first 12 seconds). "
        "Review objective loudness, true peak, LRA, brightness (spectral centroid), and peak polyphony."
    )

    if st.button("🔄 Render / Re-render Audition Clips"):
        with st.spinner("Rendering procedural audio audition clips..."):
            run_sound_audition()
        st.success("Audition render complete!")

    manifest_path = Path("build/sound_audition/manifest.json")
    if not manifest_path.exists():
        st.warning("Audition manifest not found in `build/sound_audition/`. Click 'Render Audition Clips' above.")
    else:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        presets = manifest.get("presets", [])
        for p in presets:
            with st.expander(
                f"🔊 {p['preset']} (Palette: {p['palette']}, Scale: {p['scale']}, Root: {p['root']}, Wet: {p['reverb_wet']})",
                expanded=False,
            ):
                col_player, col_metrics = st.columns([1, 1])
                with col_player:
                    st.write("**Audio Player:**")
                    wav_file = Path(p["wav_path"])
                    if wav_file.exists():
                        st.audio(str(wav_file), format="audio/wav")
                    else:
                        st.error(f"File not found: {wav_file}")

                with col_metrics:
                    st.write("**Objective Audio Report:**")
                    st.markdown(
                        f"- **Integrated Loudness:** `{p['integrated_lufs']:.2f}` LUFS (Target: -14 LUFS)\n"
                        f"- **True Peak:** `{p['true_peak']:.2f}` dBTP (Target: <= -1.5 dBTP)\n"
                        f"- **Loudness Range (LRA):** `{p['lra']:.2f}` LU\n"
                        f"- **Spectral Centroid (Brightness):** `{p['spectral_centroid_hz']:.1f}` Hz\n"
                        f"- **Onsets / sec:** `{p['onsets_per_sec']:.2f}`\n"
                        f"- **Peak Polyphony:** `{p['peak_polyphony']}` voices\n"
                    )


# ---------------------------------------------------------------------------
# Tab 2: Blind Test
# ---------------------------------------------------------------------------
with tab_blind:
    st.header("Blind Preset Evaluation")
    st.markdown(
        "Evaluate presets anonymously without brand or timbre bias. "
        "Score pleasantness from 1 to 5 and indicate whether you would keep watching the short."
    )

    manifest_path = Path("build/sound_audition/manifest.json")
    if not manifest_path.exists():
        st.warning("Audition clips not found. Please render them in the Audition tab first.")
    else:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        presets = manifest.get("presets", [])

        # Shuffled anonymous mapping in session state
        if "blind_sound_map" not in st.session_state:
            shuffled = list(presets)
            random.seed(1337)
            random.shuffle(shuffled)
            labels = [f"Preset {chr(65 + i)}" for i in range(len(shuffled))]  # Preset A, B, C...
            st.session_state.blind_sound_map = list(zip(labels, shuffled))

        listener_name = st.text_input("Your Name / Listener ID:", value="Listener 1", key="blind_listener_name")

        for anon_label, p in st.session_state.blind_sound_map:
            with st.container():
                st.subheader(f"🎧 {anon_label}")
                wav_file = Path(p["wav_path"])
                if wav_file.exists():
                    st.audio(str(wav_file), format="audio/wav")

                col_score, col_keep = st.columns([1, 1])
                with col_score:
                    score = st.slider(
                        f"Pleasantness (1 = Harsh/Annoying, 5 = Satisfying/Musical):",
                        min_value=1,
                        max_value=5,
                        value=4,
                        key=f"score_{anon_label}",
                    )
                with col_keep:
                    keep_watching = st.radio(
                        "Would you keep watching this short?",
                        options=["Yes", "No"],
                        index=0,
                        horizontal=True,
                        key=f"keep_{anon_label}",
                    )

                if st.button(f"Submit Evaluation for {anon_label}", key=f"btn_{anon_label}"):
                    record_sound_evaluation(
                        listener=listener_name,
                        preset_id=p["preset"],
                        sim_id="ellipse_billiards",
                        score=score,
                        keep_watching=(keep_watching == "Yes"),
                        blind=True,
                    )
                    st.success(f"Evaluation for {anon_label} saved!")


# ---------------------------------------------------------------------------
# Tab 3: Results & Acceptance
# ---------------------------------------------------------------------------
with tab_results:
    st.header("Preset Acceptance Results")
    st.markdown(
        f"**Acceptance Rules (SPEC Section 22.5):**\n"
        f"- Minimum listeners: **{ACCEPTANCE_RULES['min_listeners']}**\n"
        f"- Mean pleasantness: **>= {ACCEPTANCE_RULES['min_pleasantness']:.1f} / 5.0**\n"
        f"- Would keep watching rate: **>= {ACCEPTANCE_RULES['min_keep_watching_pct']:.0f}%**\n"
    )

    scores = load_sound_scores()
    if not scores:
        st.info("No evaluations recorded yet. Complete blind reviews in Tab 2.")
    else:
        aggregates = aggregate_sound_scores(scores)
        rows = []
        for pid, stats in aggregates.items():
            status_badge = "✅ PASSED" if stats["passed"] else "❌ FAILED"
            rows.append({
                "Preset": pid,
                "Listeners": f"{stats['listener_count']} / {ACCEPTANCE_RULES['min_listeners']}",
                "Mean Pleasantness": f"{stats['mean_pleasantness']:.2f} / 5.0",
                "Keep Watching %": f"{stats['keep_watching_pct']:.1f}%",
                "Status": status_badge,
                "Failure Reasons": "; ".join(stats["failure_reasons"]) if stats["failure_reasons"] else "None",
            })

        st.dataframe(rows, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 4: Approve Preset
# ---------------------------------------------------------------------------
with tab_approve:
    st.header("Approve Sound Preset")
    scores = load_sound_scores()
    aggregates = aggregate_sound_scores(scores) if scores else {}

    candidate_names = [label for label, _, _ in AUDITION_PRESETS]
    selected_preset = st.selectbox("Select Preset to Approve:", candidate_names)

    stats = aggregates.get(selected_preset)
    is_passing = stats["passed"] if stats else False

    if is_passing:
        st.success(f"Preset `{selected_preset}` meets all acceptance criteria!")
    else:
        st.warning(f"Preset `{selected_preset}` does not currently meet acceptance criteria.")

    allow_override = st.checkbox("Allow override with justification", value=False)
    override_reason = st.text_input("Override Reason (required if overriding):", value="")

    if st.button("Approve Preset"):
        try:
            record = approve_preset(
                preset_id=selected_preset,
                sim_id="ellipse_billiards",
                allow_override=allow_override,
                override_reason=override_reason,
            )
            st.success(f"Approved preset `{selected_preset}` successfully!")
            st.json(record)
        except Exception as e:
            st.error(f"Approval failed: {e}")


# ---------------------------------------------------------------------------
# Tab 5: Assign to Simulation
# ---------------------------------------------------------------------------
with tab_assign:
    st.header("Assign Sound Preset to Simulation")
    st.markdown("Writes the `sound_palette` configuration block into `sims/<id>/sim_spec.json`.")

    sim_id = st.text_input("Simulation directory:", value="sims/ellipse_billiards")
    preset_choice = st.selectbox("Select Preset:", [label for label, _, _ in AUDITION_PRESETS], index=1)

    if st.button("Assign Preset to Simulation"):
        try:
            spec_file = assign_palette_to_sim(preset_choice, sim_dir=sim_id)
            st.success(f"Assigned preset `{preset_choice}` to `{spec_file}`!")
            with open(spec_file, "r", encoding="utf-8") as f:
                updated_spec = json.load(f)
            st.json(updated_spec.get("sound_palette", {}))
        except Exception as e:
            st.error(f"Assignment failed: {e}")
