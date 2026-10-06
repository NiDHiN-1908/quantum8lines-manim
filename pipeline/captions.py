"""
Caption generation (ASS with word-by-word highlight and plain SRT), verification,
and FFmpeg burning helper.
Follows SPEC.md Section 11 and Milestone M3b Step 2.
"""

from pathlib import Path
import json
import re
import difflib
import subprocess
from typing import Dict, Any, List, Tuple, Union, Optional

from core.tokens import HIGHLIGHT, BACKGROUND, TEXT
from core.layout import Layout, LAYOUT_169, LAYOUT_916


def hex_to_ass_color(hex_color: Any, alpha: int = 0) -> str:
    """
    Converts a standard hex color (#RRGGBB or #RGB) or ManimColor into ASS color format:
    &H<alpha><blue><green><red>& (e.g. &H004444FF& for #ff4444).
    """
    cleaned = str(hex_color).strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join([c * 2 for c in cleaned])
    if len(cleaned) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")

    r = int(cleaned[0:2], 16)
    g = int(cleaned[2:4], 16)
    b = int(cleaned[4:6], 16)

    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"


def format_ass_time(seconds: float) -> str:
    """Formats seconds into ASS timestamp format H:MM:SS.cc (centiseconds)."""
    total_cs = max(0, int(round(seconds * 100)))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def format_srt_time(seconds: float) -> str:
    """Formats seconds into SRT timestamp format HH:MM:SS,mmm (milliseconds)."""
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def chunk_words(
    words: List[Dict[str, Any]],
    min_words: int = 3,
    max_words: int = 5,
) -> List[List[Dict[str, Any]]]:
    """
    Groups a list of word timestamp dictionaries into chunks of 3 to 5 words,
    distributed as evenly as possible.
    """
    if not words:
        return []
    n = len(words)
    if n <= max_words:
        return [words]

    # Determine number of chunks k such that min_words * k <= n <= max_words * k
    k = max(1, (n + max_words - 1) // max_words)
    while k * min_words > n and k > 1:
        k -= 1
    if k == 0:
        k = 1

    base_size = n // k
    remainder = n % k
    chunks = []
    idx = 0
    for i in range(k):
        size = base_size + (1 if i < remainder else 0)
        chunks.append(words[idx : idx + size])
        idx += size
    return chunks


def _load_timings(timings_input: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """Helper to load timings JSON data."""
    if isinstance(timings_input, dict):
        return timings_input
    p = Path(timings_input)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_ass(
    timings_input: Union[str, Path, Dict[str, Any]],
    layout: Layout = LAYOUT_169,
    font_size: Optional[int] = None,
) -> str:
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle string with word-by-word highlight.
    - Style: Inter Bold, white text, active word in HIGHLIGHT color, dark outline.
    - Positioned inside the caption region of the specified layout.
    - At most 2 lines, 3-5 words visible at a time.
    """
    timings = _load_timings(timings_input)
    is_portrait = layout.frame_height > layout.frame_width

    # Typography sizing (SPEC Section 4.3 minimums: body >= 32 px landscape, >= 38 px portrait)
    if font_size is None:
        font_size = 46 if is_portrait else 38

    # Colors
    primary_color = "&H00FFFFFF&"                  # White text
    highlight_color = hex_to_ass_color(HIGHLIGHT)   # Active word highlight color
    outline_color = hex_to_ass_color(BACKGROUND)   # Dark outline matching background token

    # Vertical positioning inside layout caption region
    caption_region = layout.regions["caption"]
    # Calculate bottom margin in pixels from screen bottom
    bottom_units = caption_region.center_y - (caption_region.height / 2.0)
    screen_y_bottom = (layout.pixel_height / 2.0) - (bottom_units * layout.px_per_unit)
    margin_v = int(round(layout.pixel_height - screen_y_bottom))

    # Horizontal margins
    margin_h = int(round(layout.safe_left_px))

    header = f"""[Script Info]
; Quantum8Lines Automated Captions
ScriptType: v4.00+
PlayResX: {layout.pixel_width}
PlayResY: {layout.pixel_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Inter,{font_size},{primary_color},&H000000FF&,{outline_color},&H80000000&,-1,0,0,0,100,100,0,0,1,3.5,0.0,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    lines = timings.get("lines", [])

    for line in lines:
        words = line.get("words", [])
        if not words:
            continue

        chunks = chunk_words(words, min_words=3, max_words=5)

        for chunk in chunks:
            chunk_start = chunk[0].get("absolute_start", chunk[0].get("start", 0.0))
            chunk_end = chunk[-1].get("absolute_end", chunk[-1].get("end", chunk_start + 1.0))

            for i, active_word in enumerate(chunk):
                w_start = active_word.get("absolute_start", active_word.get("start", chunk_start))
                # Active word duration extends to next word start or chunk end
                if i + 1 < len(chunk):
                    w_end = chunk[i + 1].get("absolute_start", chunk[i + 1].get("start", w_start + 0.3))
                else:
                    w_end = chunk_end

                # Format dialogue text: words before active, active highlighted, words after
                before_words = " ".join([w["word"] for w in chunk[:i]])
                after_words = " ".join([w["word"] for w in chunk[i + 1:]])
                active_text = active_word["word"]

                formatted_parts = []
                if before_words:
                    formatted_parts.append(before_words)
                formatted_parts.append(f"{{\\c{highlight_color}}}{active_text}{{\\c{primary_color}}}")
                if after_words:
                    formatted_parts.append(after_words)

                event_text = " ".join(formatted_parts)
                start_str = format_ass_time(w_start)
                end_str = format_ass_time(w_end)

                events.append(
                    f"Dialogue: 0,{start_str},{end_str},Caption,,0,0,0,,{event_text}"
                )

    return header + "\n".join(events) + "\n"


def generate_srt(
    timings_input: Union[str, Path, Dict[str, Any]],
    min_words: int = 3,
    max_words: int = 5,
) -> str:
    """
    Generates plain SubRip (.srt) subtitles without styling tags.
    """
    timings = _load_timings(timings_input)
    lines = timings.get("lines", [])
    srt_entries = []
    counter = 1

    for line in lines:
        words = line.get("words", [])
        if not words:
            continue

        chunks = chunk_words(words, min_words=min_words, max_words=max_words)
        for chunk in chunks:
            chunk_start = chunk[0].get("absolute_start", chunk[0].get("start", 0.0))
            chunk_end = chunk[-1].get("absolute_end", chunk[-1].get("end", chunk_start + 1.0))
            chunk_text = " ".join([w["word"] for w in chunk])

            start_str = format_srt_time(chunk_start)
            end_str = format_srt_time(chunk_end)

            srt_entries.append(
                f"{counter}\n{start_str} --> {end_str}\n{chunk_text}\n"
            )
            counter += 1

    return "\n".join(srt_entries)


def check_caption_text(
    script_input: Union[str, Path, Dict[str, Any]],
    captions_input: Union[str, Path],
) -> Tuple[bool, str]:
    """
    Verifies that caption words match script words exactly (ignoring case and punctuation).
    Returns (True, "OK") or (False, diff_description).
    """
    # 1. Extract script words
    if isinstance(script_input, dict):
        script_data = script_input
    elif Path(script_input).exists():
        with open(script_input, "r", encoding="utf-8") as f:
            script_data = json.load(f)
    else:
        script_data = {"lines": [{"text": str(script_input)}]}

    script_lines = script_data.get("lines", [])
    raw_script_text = " ".join([l.get("text", "") for l in script_lines])
    script_words = re.sub(r"[^\w\s]", "", raw_script_text).lower().split()

    # 2. Extract caption words
    if Path(captions_input).exists():
        caption_content = Path(captions_input).read_text(encoding="utf-8")
    else:
        caption_content = str(captions_input)

    # Strip ASS formatting tags {\...} and dialogue headers
    clean_lines = []
    for line in caption_content.splitlines():
        if line.startswith("Dialogue:"):
            # ASS line: extract payload after 9th comma
            parts = line.split(",", 9)
            if len(parts) == 10:
                payload = parts[9]
                clean_lines.append(re.sub(r"\{.*?\}", "", payload))
        elif "-->" in line or line.strip().isdigit() or not line.strip():
            # SRT line timing or counter
            continue
        elif not line.startswith("[") and not line.startswith("Format:") and not line.startswith("Style:"):
            clean_lines.append(line)

    caption_text = " ".join(clean_lines)
    caption_words = re.sub(r"[^\w\s]", "", caption_text).lower().split()

    # Deduplicate repeated words in consecutive chunk-highlight events
    deduped_caption_words = []
    # If it's an ASS with word-by-word duplicate frames, extract unique sequence
    # Compare with script words directly using sequence matcher
    matcher = difflib.SequenceMatcher(None, script_words, caption_words)
    # Check if all script words are covered in order
    script_joined = " ".join(script_words)
    # For SRT or deduplicated words:
    # A simple token-presence match:
    unique_words_in_order = []
    prev_w = None
    for w in caption_words:
        if w != prev_w:
            unique_words_in_order.append(w)
            prev_w = w

    if script_words == unique_words_in_order or script_words == caption_words:
        return True, "Caption text matches script words exactly."

    # Compare set and sequence
    diff = list(difflib.unified_diff(
        script_words,
        unique_words_in_order,
        fromfile="script",
        tofile="captions",
        lineterm=""
    ))

    if not diff:
        return True, "Caption text matches script words exactly."

    diff_str = "\n".join(diff)
    return False, f"Caption mismatch detected:\n{diff_str}"


def burn_captions(
    video_in: Union[str, Path],
    ass_path: Union[str, Path],
    video_out: Union[str, Path],
    fonts_dir: Union[str, Path] = Path("brand/fonts"),
) -> Path:
    """
    Burns ASS subtitles into a video file using FFmpeg's subtitles filter.
    Handles Windows path escaping (colons and backslashes) properly.
    """
    p_in = Path(video_in).resolve()
    p_ass = Path(ass_path).resolve()
    p_out = Path(video_out).resolve()
    p_fonts = Path(fonts_dir).resolve()
    p_out.parent.mkdir(parents=True, exist_ok=True)

    if not p_in.exists():
        raise FileNotFoundError(f"Input video not found: {p_in}")
    if not p_ass.exists():
        raise FileNotFoundError(f"ASS subtitle file not found: {p_ass}")

    # FFmpeg subtitles filter path escaping on Windows:
    # 1. Use forward slashes
    # 2. Escape colon in drive letter (e.g. C\: -> C\:/)
    # 3. Escape single quotes inside paths
    escaped_ass = str(p_ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    escaped_fonts = str(p_fonts).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    vf = f"subtitles='{escaped_ass}':fontsdir='{escaped_fonts}'"

    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(p_in),
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(p_out),
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg caption burn failed:\n{proc.stderr}")

    return p_out


def generate_caption_proofs(
    temp_dir: Path = Path("temp_renders"),
    audition_set_path: Path = Path("brand/voices/audition_set.json"),
) -> Dict[str, Path]:
    """
    Produces visual proofs:
    Burns captions for one audition line onto a blank dark 5 s video in both layouts,
    and extracts one frame from each to temp_renders/caption_169.png and caption_916.png.
    """
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Synthetic timing for the first audition line
    proof_timings = {
        "chapter": "caption_proof",
        "profile_id": "proof_profile",
        "sample_rate": 24000,
        "total_duration": 4.5,
        "lines": [
            {
                "id": "hook",
                "beat": "hook",
                "text": "What if some arrows refuse to turn, no matter how hard you push?",
                "start": 0.0,
                "end": 4.2,
                "duration": 4.2,
                "words": [
                    {"word": "What", "start": 0.0, "end": 0.25, "absolute_start": 0.0, "absolute_end": 0.25},
                    {"word": "if", "start": 0.25, "end": 0.50, "absolute_start": 0.25, "absolute_end": 0.50},
                    {"word": "some", "start": 0.50, "end": 0.85, "absolute_start": 0.50, "absolute_end": 0.85},
                    {"word": "arrows", "start": 0.85, "end": 1.40, "absolute_start": 0.85, "absolute_end": 1.40},
                    {"word": "refuse", "start": 1.40, "end": 1.95, "absolute_start": 1.40, "absolute_end": 1.95},
                    {"word": "to", "start": 1.95, "end": 2.20, "absolute_start": 1.95, "absolute_end": 2.20},
                    {"word": "turn,", "start": 2.20, "end": 2.65, "absolute_start": 2.20, "absolute_end": 2.65},
                    {"word": "no", "start": 2.65, "end": 2.90, "absolute_start": 2.65, "absolute_end": 2.90},
                    {"word": "matter", "start": 2.90, "end": 3.30, "absolute_start": 2.90, "absolute_end": 3.30},
                    {"word": "how", "start": 3.30, "end": 3.55, "absolute_start": 3.30, "absolute_end": 3.55},
                    {"word": "hard", "start": 3.55, "end": 3.85, "absolute_start": 3.55, "absolute_end": 3.85},
                    {"word": "you", "start": 3.85, "end": 4.05, "absolute_start": 3.85, "absolute_end": 4.05},
                    {"word": "push?", "start": 4.05, "end": 4.40, "absolute_start": 4.05, "absolute_end": 4.40},
                ],
            }
        ],
    }

    proofs = {}
    for layout_key, layout in [("169", LAYOUT_169), ("916", LAYOUT_916)]:
        ass_content = generate_ass(proof_timings, layout=layout)
        ass_file = temp_dir / f"proof_{layout_key}.ass"
        ass_file.write_text(ass_content, encoding="utf-8")

        # 1. Generate 5-second blank dark video (#0e0e11)
        blank_video = temp_dir / f"blank_{layout_key}.mp4"
        cmd_blank = [
            "ffmpeg", "-y", "-nostdin",
            "-f", "lavfi",
            "-i", f"color=c=#0e0e11:s={layout.pixel_width}x{layout.pixel_height}:d=5:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(blank_video),
        ]
        subprocess.run(cmd_blank, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 2. Burn subtitles onto video
        burned_video = temp_dir / f"burned_{layout_key}.mp4"
        burn_captions(blank_video, ass_file, burned_video)

        # 3. Extract sample frame at t=1.0s (where active word is highlighted)
        proof_png = temp_dir / f"caption_{layout_key}.png"
        cmd_frame = [
            "ffmpeg", "-y", "-nostdin",
            "-ss", "00:00:01.000",
            "-i", str(burned_video),
            "-frames:v", "1",
            str(proof_png),
        ]
        subprocess.run(cmd_frame, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proofs[layout_key] = proof_png

        # Clean up intermediate videos
        blank_video.unlink(missing_ok=True)
        burned_video.unlink(missing_ok=True)
        ass_file.unlink(missing_ok=True)

    return proofs
