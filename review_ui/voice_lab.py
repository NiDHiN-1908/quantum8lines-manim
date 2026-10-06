"""
Quantum8Lines Voice Lab - Streamlit Review UI
Run with: uv run streamlit run review_ui/voice_lab.py
Follows SPEC.md Section 10 and Milestone M3b Step 3.
"""

from pathlib import Path
import json
import random
import streamlit as st

from review_ui.voice_lab_logic import (
    ACCEPTANCE_RULES,
    DEFAULT_SCORES_PATH,
    DEFAULT_VOICES_DIR,
    load_scores,
    record_evaluation,
    aggregate_scores,
    approve_profile,
    assign_profile_to_topic,
)
from pipeline.audition import (
    DEFAULT_AUDITION_SET_PATH,
    get_candidate_profiles,
    render_audition_set,
)


st.set_page_config(
    page_title="Quantum8Lines Voice Lab",
    page_icon="🎙️",
    layout="wide",
)

st.title("🎙️ Quantum8Lines Voice Lab")
st.caption("Pedagogical voice audition, blind evaluation, approval, and topic assignment.")


# ---------------------------------------------------------------------------
# Tabs Navigation
# ---------------------------------------------------------------------------
tab_audition, tab_blind, tab_results, tab_approve, tab_assign = st.tabs([
    "1. Audition",
    "2. Blind Test",
    "3. Results & Acceptance",
    "4. Approve Profile",
    "5. Assign to Topic",
])


# ---------------------------------------------------------------------------
# Tab 1: Audition
# ---------------------------------------------------------------------------
with tab_audition:
    st.header("Candidate Voice Audition")
    st.markdown(
        "Listen to candidate voices across 5 pedagogical beats "
        "(hook, explain, equation, aha, close). Compare raw vs warm_narration postfx."
    )

    if st.button("🔄 Render Missing Audition Clips"):
        with st.spinner("Rendering audition clips across candidate profiles..."):
            render_audition_set()
        st.success("Audition render complete!")

    manifest_path = Path("build/voice_audition/manifest.json")
    if not manifest_path.exists():
        st.warning("Audition manifest not found in `build/voice_audition/`. Click 'Render Missing Audition Clips' above.")
    else:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        profiles = manifest.get("profiles", [])
        for p in profiles:
            with st.expander(f"🔊 {p['profile_id']} (Voice: {p['voice']}, Tone: {p['tone']}, Speed: {p['speed']})", expanded=False):
                col_mode, col_full = st.columns([1, 2])
                with col_mode:
                    variant = st.radio(
                        "Variant",
                        ["PostFX (warm_narration)", "Raw"],
                        key=f"var_{p['profile_id']}",
                        horizontal=True,
                    )
                with col_full:
                    st.write("**Full Concatenated Narration:**")
                    full_wav = p["narration_postfx_wav"] if "PostFX" in variant else p["narration_wav"]
                    if Path(full_wav).exists():
                        st.audio(full_wav, format="audio/wav")

                st.write("**Individual Lines:**")
                line_map = p.get("lines_postfx" if "PostFX" in variant else "lines_raw", {})
                cols = st.columns(len(line_map)) if line_map else [st]
                for idx, (lid, lpath) in enumerate(line_map.items()):
                    with cols[idx % len(cols)]:
                        st.caption(f"Beat: `{lid}`")
                        if Path(lpath).exists():
                            st.audio(lpath, format="audio/wav")


# ---------------------------------------------------------------------------
# Tab 2: Blind Test
# ---------------------------------------------------------------------------
with tab_blind:
    st.header("Double-Blind Voice Evaluation")
    st.markdown(
        "Candidate profiles are presented anonymously with shuffled labels. "
        "Listeners rate **Naturalness (1-5)** and answer **Would Keep Watching (Yes/No)**. "
        "The voice mapping is revealed only after ratings are saved."
    )

    listener_name = st.text_input("Listener Name / ID", placeholder="e.g. Listener 1").strip()
    uploaded_ref = st.file_uploader("Optional: Upload human reference audio clip for baseline comparison", type=["wav", "mp3"])

    manifest_path = Path("build/voice_audition/manifest.json")
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        profiles = manifest.get("profiles", [])

        # Stable pseudo-random shuffle per session
        if "blind_order" not in st.session_state:
            items = list(profiles)
            random.shuffle(items)
            st.session_state["blind_order"] = items

        evaluations_to_save = []
        labels = [f"Voice {chr(65 + i)}" for i in range(len(st.session_state["blind_order"]))]

        with st.form("blind_eval_form"):
            for label, p in zip(labels, st.session_state["blind_order"]):
                st.subheader(label)
                # Play postfx variant
                wav_path = p.get("narration_postfx_wav", p.get("narration_wav"))
                if Path(wav_path).exists():
                    st.audio(wav_path, format="audio/wav")

                col_s, col_k = st.columns(2)
                with col_s:
                    score = st.slider(f"Naturalness Score (1=Robotic, 5=Humanlike)", 1, 5, 3, key=f"score_{label}")
                with col_k:
                    kw = st.radio(f"Would keep watching?", ["Yes", "No"], key=f"kw_{label}", horizontal=True)

                evaluations_to_save.append({
                    "label": label,
                    "profile_id": p["profile_id"],
                    "line_id": "full_narration",
                    "score": score,
                    "keep_watching": kw == "Yes",
                })
                st.divider()

            submitted = st.form_submit_button("💾 Submit Blind Evaluations")
            if submitted:
                if not listener_name:
                    st.error("Please enter a Listener Name before submitting.")
                else:
                    for ev in evaluations_to_save:
                        record_evaluation(
                            listener=listener_name,
                            profile_id=ev["profile_id"],
                            line_id=ev["line_id"],
                            score=ev["score"],
                            keep_watching=ev["keep_watching"],
                            blind=True,
                        )
                    st.success("Evaluations saved to `brand/voices/scores.json`!")
                    st.session_state["show_mapping"] = True

        if st.session_state.get("show_mapping"):
            st.info("### 🔍 Revealed Anonymous Mapping")
            for label, p in zip(labels, st.session_state["blind_order"]):
                st.write(f"- **{label}** -> `{p['profile_id']}` (Voice: `{p['voice']}`, Tone: `{p['tone']}`)")


# ---------------------------------------------------------------------------
# Tab 3: Results & Acceptance Rules
# ---------------------------------------------------------------------------
with tab_results:
    st.header("Voice Lab Evaluation Results")
    st.markdown(
        f"**Acceptance Rule (Starting Assumption):**\n"
        f"- At least **{ACCEPTANCE_RULES['min_listeners']}** listeners\n"
        f"- Mean naturalness score $\\ge$ **{ACCEPTANCE_RULES['min_naturalness']:.1f}** / 5.0\n"
        f"- Keep-watching rate $\\ge$ **{ACCEPTANCE_RULES['min_keep_watching_pct']:.0f}%**"
    )

    scores = load_scores()
    if not scores:
        st.info("No evaluations recorded yet in `brand/voices/scores.json`. Complete evaluations in the Blind Test tab.")
    else:
        aggregates = aggregate_scores(scores)
        table_rows = []
        for pid, stats in aggregates.items():
            table_rows.append({
                "Profile ID": pid,
                "Listeners": stats["listener_count"],
                "Total Ratings": stats["evaluations_count"],
                "Mean Naturalness": f"{stats['mean_naturalness']:.2f} / 5.0",
                "Keep Watching %": f"{stats['keep_watching_pct']:.1f}%",
                "Status": "✅ PASS" if stats["passed"] else "❌ FAIL",
                "Notes": ", ".join(stats["failure_reasons"]) if stats["failure_reasons"] else "Meets criteria",
            })
        st.dataframe(table_rows, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 4: Approve Profile
# ---------------------------------------------------------------------------
with tab_approve:
    st.header("Approve Voice Profile")
    st.markdown(
        "Only approved profiles can be assigned to topics for final video rendering. "
        "A profile can only be approved if it satisfies the acceptance rule, or if approved with a documented override."
    )

    candidate_files = sorted(Path("brand/voices").glob("*.json"))
    candidate_profiles = [p.stem for p in candidate_files if p.name not in ["audition_set.json", "scores.json"]]

    selected_pid = st.selectbox("Select Profile", candidate_profiles)
    if selected_pid:
        p_path = Path("brand/voices") / f"{selected_pid}.json"
        with open(p_path, "r", encoding="utf-8") as f:
            p_data = json.load(f)

        st.json(p_data)
        scores = load_scores()
        agg = aggregate_scores(scores).get(selected_pid, {})
        has_passed = agg.get("passed", False)

        col_app, col_ovr = st.columns(2)
        with col_app:
            if st.button("✅ Approve Profile (Meets Criteria)", disabled=not has_passed):
                res = approve_profile(selected_pid)
                st.success(f"Profile `{selected_pid}` approved!")
                st.rerun()

        with col_ovr:
            with st.expander("⚠️ Approve with Override"):
                override_reason = st.text_area("Reason for override", placeholder="e.g. Channel director artistic preference.")
                if st.button("Force Approval with Override"):
                    try:
                        res = approve_profile(selected_pid, allow_override=True, override_reason=override_reason)
                        st.success(f"Profile `{selected_pid}` approved with override!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


# ---------------------------------------------------------------------------
# Tab 5: Assign to Topic
# ---------------------------------------------------------------------------
with tab_assign:
    st.header("Assign Voice Profile to Topic")
    st.markdown("Assign an approved voice profile to a topic's `bible.json`.")

    # Find approved profiles only
    approved_profiles = []
    for f in sorted(Path("brand/voices").glob("*.json")):
        if f.name in ["audition_set.json", "scores.json"]:
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            if d.get("status") == "approved":
                approved_profiles.append(d["id"])
        except Exception:
            continue

    if not approved_profiles:
        st.warning("No approved voice profiles available. Approve at least one profile in the 'Approve Profile' tab first.")
    else:
        chosen_profile = st.selectbox("Select Approved Voice Profile", approved_profiles)
        topics_dir = Path("topics")
        existing_topics = [d.name for d in topics_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

        topic_choice = st.selectbox("Select Existing Topic or enter new topic below", ["<Enter New Topic>"] + existing_topics)
        if topic_choice == "<Enter New Topic>":
            target_topic = st.text_input("New Topic Slug", placeholder="linear_algebra").strip()
        else:
            target_topic = topic_choice

        if st.button("📌 Assign to Topic"):
            if not target_topic:
                st.error("Please enter or select a topic.")
            else:
                topic_path = topics_dir / target_topic
                bible_path, created_minimal = assign_profile_to_topic(chosen_profile, topic_path)
                msg = f"Assigned `{chosen_profile}` to `{bible_path}`."
                if created_minimal:
                    msg += " (Created minimal bible.json since none existed)."
                st.success(msg)
