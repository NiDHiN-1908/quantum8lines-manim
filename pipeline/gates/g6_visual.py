"""
Quality Gate G6: Visual QA Verification (SPEC.md Section 9 & Milestone M4b).
Deterministic evaluation from recorded scene snapshots per layout (16:9 and 9:16):
- G6a_inside_safe: Every essential object and text mobject is inside the safe zone.
- G6b_no_overlap: No pair of essential/text objects overlap (except within same group).
- G6c_min_text_size: Text height meets SPEC 4.3 minimums (48 px labels, 72 px keywords).
- G6d_contrast: Text color against BACKGROUND (#0e0e11) meets WCAG >= 4.5 contrast ratio.
- G6e_expect_visible: Every expect.visible item from storyboard exists and lies inside the frame.
- G6f_characters: Character objects do not intersect essential objects, and max 2 on screen.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from core.layout import Layout, LAYOUT_169, LAYOUT_916
from pipeline.gates.models import Check, GateConfig, GateResult

BACKGROUND_HEX = "#0e0e11"


# ---------------------------------------------------------------------------
# WCAG Contrast Calculation Helpers
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    """Parse hex color string to normalized (r, g, b) float tuple in [0, 1]."""
    clean = hex_str.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean])
    elif len(clean) == 8:
        clean = clean[:6]
    r = int(clean[0:2], 16) / 255.0
    g = int(clean[2:4], 16) / 255.0
    b = int(clean[4:6], 16) / 255.0
    return r, g, b


def channel_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(r: float, g: float, b: float) -> float:
    return (
        0.2126 * channel_to_linear(r)
        + 0.7152 * channel_to_linear(g)
        + 0.0722 * channel_to_linear(b)
    )


def compute_contrast_ratio(color_a: str, color_b: str = BACKGROUND_HEX) -> float:
    """Compute WCAG 2.1 relative luminance contrast ratio between two hex colors."""
    try:
        r1, g1, b1 = hex_to_rgb(color_a)
        r2, g2, b2 = hex_to_rgb(color_b)
        l1 = relative_luminance(r1, g1, b1)
        l2 = relative_luminance(r2, g2, b2)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# Bounding Box Intersection Helpers
# ---------------------------------------------------------------------------

def compute_box_intersection(
    box_a: List[float], box_b: List[float], tol: float = 0.02
) -> Optional[Tuple[float, float]]:
    """
    Compute intersection between two 2D boxes [x_min, y_min, x_max, y_max].
    Returns (overlap_width, overlap_height) if overlapping by more than tolerance.
    """
    x_min = max(box_a[0], box_b[0])
    y_min = max(box_a[1], box_b[1])
    x_max = min(box_a[2], box_b[2])
    y_max = min(box_a[3], box_b[3])

    w = x_max - x_min
    h = y_max - y_min

    if w > tol and h > tol:
        return (round(w, 4), round(h, 4))
    return None


def run_g6_visual(
    chapter_dir: Optional[Union[str, Path]] = None,
    snapshots: Optional[List[Dict[str, Any]]] = None,
    storyboard_data: Optional[Dict[str, Any]] = None,
    layout: Union[str, Layout] = "16:9",
    config: Optional[GateConfig] = None,
    gate_id: Optional[str] = None,
) -> GateResult:
    """
    Execute Quality Gate G6: Visual QA from recorded snapshots for a specific layout.
    """
    cfg = config or GateConfig()
    checks: List[Check] = []

    # 1. Resolve layout object
    if isinstance(layout, Layout):
        target_layout = layout
        slug = "169" if target_layout.name in ("16:9", "169") else "916"
    elif str(layout) in ("16:9", "169"):
        target_layout = LAYOUT_169
        slug = "169"
    elif str(layout) in ("9:16", "916"):
        target_layout = LAYOUT_916
        slug = "916"
    else:
        raise ValueError(f"Unsupported layout: {layout}")

    # 2. Resolve snapshots
    ch_path = Path(chapter_dir).resolve() if chapter_dir else None
    if snapshots is None and ch_path is not None:
        snap_file = ch_path / "qa" / f"snapshots_{slug}.json"
        if snap_file.exists():
            with open(snap_file, "r", encoding="utf-8") as f:
                snapshots = json.load(f)

    if snapshots is None:
        checks.append(
            Check(
                id="G6_snapshots_available",
                passed=False,
                severity="error",
                message=f"No snapshots available for layout {target_layout.name}.",
                details={"layout": slug},
            )
        )
        return GateResult.create(f"G6_{slug}", checks)

    # 3. Resolve storyboard
    if storyboard_data is None and ch_path is not None:
        sb_file = ch_path / "storyboard.json"
        if sb_file.exists():
            with open(sb_file, "r", encoding="utf-8") as f:
                storyboard_data = json.load(f)

    # Normalization: ensure snapshots is list of dicts
    norm_snapshots: List[Dict[str, Any]] = []
    for s in snapshots:
        if hasattr(s, "to_dict"):
            norm_snapshots.append(s.to_dict())
        elif isinstance(s, dict):
            norm_snapshots.append(s)

    # Tolerance in Manim units
    tol = cfg.visual_overlap_tolerance

    # -----------------------------------------------------------------------
    # G6a_inside_safe
    # -----------------------------------------------------------------------
    outside_safe_errors = []
    for s in norm_snapshots:
        snap_label = s.get("label", s.get("beat_id", "unknown"))
        for name, item in s.get("mobjects", {}).items():
            if item.get("essential") or item.get("kind") == "text":
                bbox = item.get("bbox", [0, 0, 0, 0])
                x_min, y_min, x_max, y_max = bbox
                breaches = []
                if x_min < target_layout.safe_x_min - tol:
                    breaches.append(f"x_min ({x_min:.2f}) < safe_x_min ({target_layout.safe_x_min:.2f})")
                if x_max > target_layout.safe_x_max + tol:
                    breaches.append(f"x_max ({x_max:.2f}) > safe_x_max ({target_layout.safe_x_max:.2f})")
                if y_min < target_layout.safe_y_min - tol:
                    breaches.append(f"y_min ({y_min:.2f}) < safe_y_min ({target_layout.safe_y_min:.2f})")
                if y_max > target_layout.safe_y_max + tol:
                    breaches.append(f"y_max ({y_max:.2f}) > safe_y_max ({target_layout.safe_y_max:.2f})")

                if breaches:
                    outside_safe_errors.append({
                        "name": name,
                        "snapshot": snap_label,
                        "kind": item.get("kind"),
                        "breaches": breaches,
                        "bbox": bbox,
                    })

    safe_passed = len(outside_safe_errors) == 0
    checks.append(
        Check(
            id="G6a_inside_safe",
            passed=safe_passed,
            severity="error",
            message=f"All essential and text objects are within {target_layout.name} safe bounds."
            if safe_passed
            else f"Safe zone breach in {target_layout.name}: {outside_safe_errors[0]['name']} at {outside_safe_errors[0]['snapshot']}: {'; '.join(outside_safe_errors[0]['breaches'])}",
            details={"layout": slug, "errors": outside_safe_errors}
            if not safe_passed
            else {"layout": slug},
        )
    )

    # -----------------------------------------------------------------------
    # G6b_no_overlap
    # -----------------------------------------------------------------------
    overlap_errors = []
    for s in norm_snapshots:
        snap_label = s.get("label", s.get("beat_id", "unknown"))
        items = list(s.get("mobjects", {}).values())
        relevant = [
            it for it in items if it.get("essential") or it.get("kind") == "text"
        ]

        for i in range(len(relevant)):
            for j in range(i + 1, len(relevant)):
                it_a = relevant[i]
                it_b = relevant[j]

                # Group exclusion: objects in same group may overlap
                grp_a = it_a.get("group")
                grp_b = it_b.get("group")
                if grp_a and grp_b and grp_a == grp_b:
                    continue

                inter = compute_box_intersection(
                    it_a.get("bbox", [0, 0, 0, 0]),
                    it_b.get("bbox", [0, 0, 0, 0]),
                    tol=tol,
                )
                if inter:
                    overlap_errors.append({
                        "snapshot": snap_label,
                        "object_a": it_a.get("name"),
                        "object_b": it_b.get("name"),
                        "overlap_w": inter[0],
                        "overlap_h": inter[1],
                    })

    overlap_passed = len(overlap_errors) == 0
    checks.append(
        Check(
            id="G6b_no_overlap",
            passed=overlap_passed,
            severity="error",
            message=f"No disallowed object overlaps detected in {target_layout.name}."
            if overlap_passed
            else f"Visual overlap detected in {target_layout.name}: '{overlap_errors[0]['object_a']}' overlaps '{overlap_errors[0]['object_b']}' in {overlap_errors[0]['snapshot']}.",
            details={"layout": slug, "errors": overlap_errors}
            if not overlap_passed
            else {"layout": slug},
        )
    )

    # -----------------------------------------------------------------------
    # G6c_min_text_size
    # -----------------------------------------------------------------------
    text_size_errors = []
    for s in norm_snapshots:
        snap_label = s.get("label", s.get("beat_id", "unknown"))
        for name, item in s.get("mobjects", {}).items():
            if item.get("kind") == "text":
                is_key = item.get("key", False)
                min_height = (
                    cfg.min_keyword_text_height_px
                    if is_key
                    else cfg.min_label_text_height_px
                )
                height_px = item.get("height_px", 0.0)

                # Tolerance: allow 0.5px margin
                if height_px < min_height - 0.5:
                    text_size_errors.append({
                        "name": name,
                        "snapshot": snap_label,
                        "text": item.get("text"),
                        "measured_px": height_px,
                        "min_required_px": min_height,
                        "is_key": is_key,
                    })

    size_passed = len(text_size_errors) == 0
    checks.append(
        Check(
            id="G6c_min_text_size",
            passed=size_passed,
            severity="error",
            message=f"All text elements meet minimum size specifications ({cfg.min_label_text_height_px:.0f}px labels, {cfg.min_keyword_text_height_px:.0f}px keywords)."
            if size_passed
            else f"Text element '{text_size_errors[0]['name']}' height {text_size_errors[0]['measured_px']:.1f}px is below required {text_size_errors[0]['min_required_px']:.0f}px.",
            details={"layout": slug, "errors": text_size_errors}
            if not size_passed
            else {"layout": slug},
        )
    )

    # -----------------------------------------------------------------------
    # G6d_contrast
    # -----------------------------------------------------------------------
    contrast_errors = []
    for s in norm_snapshots:
        snap_label = s.get("label", s.get("beat_id", "unknown"))
        for name, item in s.get("mobjects", {}).items():
            if item.get("kind") == "text":
                color = item.get("color", "")
                if color:
                    cr = compute_contrast_ratio(color, BACKGROUND_HEX)
                    if cr < cfg.min_contrast_ratio:
                        contrast_errors.append({
                            "name": name,
                            "snapshot": snap_label,
                            "text": item.get("text"),
                            "color": color,
                            "contrast_ratio": round(cr, 2),
                            "required_min": cfg.min_contrast_ratio,
                        })

    contrast_passed = len(contrast_errors) == 0
    checks.append(
        Check(
            id="G6d_contrast",
            passed=contrast_passed,
            severity="error",
            message=f"All text elements meet WCAG contrast ratio threshold (>={cfg.min_contrast_ratio})."
            if contrast_passed
            else f"Low contrast text '{contrast_errors[0]['name']}' (color {contrast_errors[0]['color']}) has contrast ratio {contrast_errors[0]['contrast_ratio']} < {cfg.min_contrast_ratio}.",
            details={"layout": slug, "errors": contrast_errors}
            if not contrast_passed
            else {"layout": slug},
        )
    )

    # -----------------------------------------------------------------------
    # G6e_expect_visible
    # -----------------------------------------------------------------------
    missing_expect_errors = []
    if storyboard_data:
        frame_x_half = target_layout.frame_width / 2.0
        frame_y_half = target_layout.frame_height / 2.0

        for b in storyboard_data.get("beats", []):
            bid = b.get("id")
            expected_names = b.get("expect", {}).get("visible", [])

            # Filter snapshots matching this beat_id
            beat_snaps = [s for s in norm_snapshots if s.get("beat_id") == bid]

            for exp_name in expected_names:
                found_inside_frame = False
                for s in beat_snaps:
                    mobs = s.get("mobjects", {})
                    if exp_name in mobs:
                        bbox = mobs[exp_name].get("bbox", [0, 0, 0, 0])
                        # Verify bbox lies inside canvas frame
                        if not (
                            bbox[2] < -frame_x_half
                            or bbox[0] > frame_x_half
                            or bbox[3] < -frame_y_half
                            or bbox[1] > frame_y_half
                        ):
                            found_inside_frame = True
                            break

                if not found_inside_frame:
                    missing_expect_errors.append({
                        "beat_id": bid,
                        "expected_object": exp_name,
                    })

    expect_passed = len(missing_expect_errors) == 0
    checks.append(
        Check(
            id="G6e_expect_visible",
            passed=expect_passed,
            severity="error",
            message="All expect.visible objects from storyboard are present on screen."
            if expect_passed
            else f"Expected object '{missing_expect_errors[0]['expected_object']}' not visible in beat '{missing_expect_errors[0]['beat_id']}'.",
            details={"layout": slug, "errors": missing_expect_errors}
            if not expect_passed
            else {"layout": slug},
        )
    )

    # -----------------------------------------------------------------------
    # G6f_characters
    # -----------------------------------------------------------------------
    char_errors = []
    for s in norm_snapshots:
        snap_label = s.get("label", s.get("beat_id", "unknown"))
        mobs = s.get("mobjects", {})

        chars = [it for it in mobs.values() if it.get("kind") == "character"]
        essentials = [
            it for it in mobs.values() if it.get("essential") and it.get("kind") != "character"
        ]

        # Check at most 2 characters present
        if len(chars) > cfg.max_character_count:
            char_errors.append({
                "snapshot": snap_label,
                "error": f"Character count {len(chars)} exceeds limit of {cfg.max_character_count}.",
            })

        # Check character does not intersect essential objects
        for c in chars:
            for ess in essentials:
                inter = compute_box_intersection(
                    c.get("bbox", [0, 0, 0, 0]),
                    ess.get("bbox", [0, 0, 0, 0]),
                    tol=tol,
                )
                if inter:
                    char_errors.append({
                        "snapshot": snap_label,
                        "character": c.get("name"),
                        "essential_object": ess.get("name"),
                        "error": f"Character '{c.get('name')}' intersects essential object '{ess.get('name')}'.",
                    })

    char_passed = len(char_errors) == 0
    checks.append(
        Check(
            id="G6f_characters",
            passed=char_passed,
            severity="error",
            message="Characters comply with screen count and do not cover essential objects."
            if char_passed
            else f"Character check failed in {target_layout.name}: {char_errors[0]['error']}",
            details={"layout": slug, "errors": char_errors}
            if not char_passed
            else {"layout": slug},
        )
    )

    return GateResult.create(gate_id or f"G6_{slug}", checks)
