"""
Lexicon management and text preparation for TTS synthesis.
Follows SPEC.md Section 10 and Milestone M3a Step 2.
"""

from pathlib import Path
import json
import re
from typing import Dict, Any, Union, Optional

DEFAULT_LEXICON_PATH = Path("brand/lexicon.json")


def load_lexicon(path: Union[str, Path] = DEFAULT_LEXICON_PATH) -> Dict[str, str]:
    """Loads pronunciation respellings dictionary from JSON file."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_text(
    line: Union[str, Dict[str, Any]],
    lexicon: Optional[Union[Dict[str, str], str, Path]] = None,
) -> str:
    """
    Applies phonetic respellings to script lines prior to TTS synthesis.
    Whole-word and case-insensitive matching.
    Per-line overrides in line['pronounce'] take precedence over the global lexicon.

    Arguments:
        line: Raw text string or script line dictionary containing 'text' and optional 'pronounce'.
        lexicon: Dictionary of respellings or path to lexicon JSON file.

    Returns:
        Prepared text string with phonetic replacements applied.
    """
    if isinstance(line, dict):
        text = str(line.get("text", ""))
        line_overrides = line.get("pronounce", {})
    else:
        text = str(line)
        line_overrides = {}

    # Load base lexicon
    if lexicon is None:
        merged_lexicon = load_lexicon(DEFAULT_LEXICON_PATH)
    elif isinstance(lexicon, (str, Path)):
        merged_lexicon = load_lexicon(lexicon)
    else:
        merged_lexicon = dict(lexicon)

    # Apply per-line overrides with higher precedence
    if line_overrides:
        merged_lexicon.update(line_overrides)

    if not merged_lexicon:
        return text

    # Sort keys by descending length so compound terms are matched before substrings
    # e.g. 'eigenvector' matches before 'eigen'
    sorted_terms = sorted(merged_lexicon.keys(), key=len, reverse=True)

    prepared = text
    for term in sorted_terms:
        replacement = merged_lexicon[term]
        # Match whole words only with case-insensitivity
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        prepared = pattern.sub(replacement, prepared)

    return prepared
