"""
Tests for captions generation (ASS with highlight, SRT), text verification,
and safe-zone layout compliance.
Follows SPEC.md Section 11 and Milestone M3b Step 2.
"""

from pathlib import Path
import pytest
import re

from core.tokens import HIGHLIGHT
from core.layout import LAYOUT_169, LAYOUT_916
from pipeline.captions import (
    hex_to_ass_color,
    format_ass_time,
    format_srt_time,
    chunk_words,
    generate_ass,
    generate_srt,
    check_caption_text,
)


@pytest.fixture
def synthetic_timings():
    return {
        "chapter": "test_chapter",
        "profile_id": "test_profile",
        "sample_rate": 24000,
        "total_duration": 5.0,
        "lines": [
            {
                "id": "l01",
                "beat": "hook",
                "text": "What if some arrows refuse to turn?",
                "start": 0.0,
                "end": 2.5,
                "duration": 2.5,
                "words": [
                    {"word": "What", "start": 0.0, "end": 0.3, "absolute_start": 0.0, "absolute_end": 0.3},
                    {"word": "if", "start": 0.3, "end": 0.6, "absolute_start": 0.3, "absolute_end": 0.6},
                    {"word": "some", "start": 0.6, "end": 1.0, "absolute_start": 0.6, "absolute_end": 1.0},
                    {"word": "arrows", "start": 1.0, "end": 1.5, "absolute_start": 1.0, "absolute_end": 1.5},
                    {"word": "refuse", "start": 1.5, "end": 1.9, "absolute_start": 1.5, "absolute_end": 1.9},
                    {"word": "to", "start": 1.9, "end": 2.1, "absolute_start": 1.9, "absolute_end": 2.1},
                    {"word": "turn?", "start": 2.1, "end": 2.5, "absolute_start": 2.1, "absolute_end": 2.5},
                ],
            }
        ],
    }


def test_hex_to_ass_color():
    """Verify conversion of hex color to ASS &HAABBGGRR& format."""
    # Red: #FF0000 -> &H000000FF&
    assert hex_to_ass_color("#FF0000") == "&H000000FF&"
    # White: #FFFFFF -> &H00FFFFFF&
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF&"
    # Token HIGHLIGHT
    ass_highlight = hex_to_ass_color(HIGHLIGHT)
    assert ass_highlight.startswith("&H00")
    assert ass_highlight.endswith("&")


def test_time_formatting():
    """Verify ASS (centiseconds) and SRT (milliseconds) time formatting."""
    assert format_ass_time(0.0) == "0:00:00.00"
    assert format_ass_time(1.234) == "0:00:01.23"
    assert format_ass_time(65.789) == "0:01:05.79"

    assert format_srt_time(0.0) == "00:00:00,000"
    assert format_srt_time(1.234) == "00:00:01,234"
    assert format_srt_time(65.789) == "00:01:05,789"


def test_chunk_words():
    """Verify words are chunked into groups of 3 to 5 words."""
    words = [{"word": f"word_{i}"} for i in range(11)]
    chunks = chunk_words(words, min_words=3, max_words=5)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert 3 <= len(chunk) <= 5

    total_words = sum(len(c) for c in chunks)
    assert total_words == len(words)


def test_generate_ass_from_synthetic_timings(synthetic_timings):
    """Verify ASS header, styles, and word-by-word highlight events."""
    ass_169 = generate_ass(synthetic_timings, layout=LAYOUT_169)
    assert "PlayResX: 1920" in ass_169
    assert "PlayResY: 1080" in ass_169
    assert "Style: Caption,Inter" in ass_169
    assert "Dialogue:" in ass_169
    # Highlight tag should be present
    highlight_code = hex_to_ass_color(HIGHLIGHT)
    assert f"{{\\c{highlight_code}}}" in ass_169

    ass_916 = generate_ass(synthetic_timings, layout=LAYOUT_916)
    assert "PlayResX: 1080" in ass_916
    assert "PlayResY: 1920" in ass_916
    assert "Style: Caption,Inter" in ass_916


def test_generate_srt_from_synthetic_timings(synthetic_timings):
    """Verify clean plain SRT output without styling tags."""
    srt = generate_srt(synthetic_timings)
    assert "1\n00:00:00,000 --> " in srt
    assert "What if some arrows" in srt
    assert "{\\c" not in srt
    assert "PlayRes" not in srt


def test_check_caption_text_positive_and_negative():
    """Verify caption text matching against script words."""
    script = {
        "lines": [
            {"id": "l01", "text": "What if some arrows refuse to turn?"}
        ]
    }
    matching_caption = "What if some arrows refuse to turn?"
    passed, msg = check_caption_text(script, matching_caption)
    assert passed is True
    assert "matches" in msg

    # Case and punctuation variations should still pass
    passed_variant, _ = check_caption_text(script, "WHAT IF SOME ARROWS REFUSE TO TURN")
    assert passed_variant is True

    # Negative case: missing or substituted words
    corrupted_caption = "What if some lines refuse to turn?"
    passed_bad, diff = check_caption_text(script, corrupted_caption)
    assert passed_bad is False
    assert "mismatch" in diff.lower() or "arrows" in diff


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_caption_position_inside_safe_zone(layout):
    """Verify caption region lies strictly within the layout safe zone."""
    cap = layout.regions["caption"]

    assert cap.x_min >= layout.safe_x_min - 1e-4, f"Caption left ({cap.x_min}) outside safe X min ({layout.safe_x_min})"
    assert cap.x_max <= layout.safe_x_max + 1e-4, f"Caption right ({cap.x_max}) outside safe X max ({layout.safe_x_max})"
    assert cap.y_min >= layout.safe_y_min - 1e-4, f"Caption bottom ({cap.y_min}) outside safe Y min ({layout.safe_y_min})"
    assert cap.y_max <= layout.safe_y_max + 1e-4, f"Caption top ({cap.y_max}) outside safe Y max ({layout.safe_y_max})"

    # For 9:16 layout, verify caption is positioned above the 480 px reserved bottom area
    if layout.name == "9:16":
        # Screen Y of caption bottom
        bottom_units = cap.center_y - (cap.height / 2.0)
        screen_y_bottom = (layout.pixel_height / 2.0) - (bottom_units * layout.px_per_unit)
        distance_from_screen_bottom = layout.pixel_height - screen_y_bottom
        assert distance_from_screen_bottom >= layout.safe_bottom_px, (
            f"Caption bottom {distance_from_screen_bottom:.1f}px is inside reserved bottom {layout.safe_bottom_px}px"
        )
