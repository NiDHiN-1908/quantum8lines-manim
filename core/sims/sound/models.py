"""
Pydantic models and preset configurations for procedural simulation sound.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class SoundPaletteSpec(BaseModel):
    """
    Configuration for procedural simulation sound.
    Validated by Pydantic with pleasant defaults.
    """
    status: str = Field(
        default="unapproved_default",
        description="Approval status: unapproved_default | candidate | approved",
    )
    palette: str = Field(
        default="marimba",
        description="Instrument timbre palette: pluck, marimba, bell, glass, legacy_ping",
    )
    scale: str = Field(
        default="pentatonic_major",
        description="Musical scale: pentatonic_major, major, natural_minor, whole_tone, lydian",
    )
    root: Union[str, float] = Field(
        default="C4",
        description="Root pitch as note name (e.g. 'C4', 'A3') or frequency in Hz",
    )
    octaves: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Number of octaves to wrap notes across",
    )
    tempo: float = Field(
        default=120.0,
        gt=20.0,
        le=300.0,
        description="BPM tempo for optional grid quantization",
    )
    grid: bool = Field(
        default=False,
        description="Whether rhythm grid quantization is enabled (off by default)",
    )
    grid_subdivision: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Grid subdivision per beat (4 = 16th notes, 2 = 8th notes, 1 = quarter)",
    )
    reverb_wet: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Wet level for Schroeder algorithmic reverb (0.0 = dry)",
    )
    reverb_decay: float = Field(
        default=1.2,
        ge=0.1,
        le=10.0,
        description="Reverb decay time in seconds (T60)",
    )
    pad_enabled: bool = Field(
        default=True,
        description="Whether the quiet generated ambient pad is enabled",
    )
    pad_gain: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description="Gain level for the ambient pad",
    )
    polyphony_limit: int = Field(
        default=24,
        ge=1,
        le=128,
        description="Maximum concurrent active voices before voice dropping",
    )
    seed: int = Field(
        default=42,
        description="Deterministic random seed for synthesis",
    )


# Standard audition and production presets
PRESET_CONFIGS: Dict[str, SoundPaletteSpec] = {
    "pluck+pentatonic": SoundPaletteSpec(
        palette="pluck",
        scale="pentatonic_major",
        root="C4",
        octaves=3,
        reverb_wet=0.15,
        reverb_decay=1.2,
        pad_enabled=True,
        pad_gain=0.05,
    ),
    "marimba+pentatonic": SoundPaletteSpec(
        palette="marimba",
        scale="pentatonic_major",
        root="C4",
        octaves=3,
        reverb_wet=0.15,
        reverb_decay=1.2,
        pad_enabled=True,
        pad_gain=0.05,
    ),
    "bell+lydian": SoundPaletteSpec(
        palette="bell",
        scale="lydian",
        root="F4",
        octaves=3,
        reverb_wet=0.22,
        reverb_decay=1.5,
        pad_enabled=True,
        pad_gain=0.05,
    ),
    "glass+whole-tone": SoundPaletteSpec(
        palette="glass",
        scale="whole_tone",
        root="C4",
        octaves=3,
        reverb_wet=0.25,
        reverb_decay=1.8,
        pad_enabled=True,
        pad_gain=0.05,
    ),
    "marimba+minor with reverb": SoundPaletteSpec(
        palette="marimba",
        scale="natural_minor",
        root="A3",
        octaves=3,
        reverb_wet=0.35,
        reverb_decay=2.0,
        pad_enabled=True,
        pad_gain=0.05,
    ),
    "pluck+major with grid quantization": SoundPaletteSpec(
        palette="pluck",
        scale="major",
        root="C4",
        octaves=3,
        grid=True,
        tempo=120.0,
        grid_subdivision=4,
        reverb_wet=0.15,
        reverb_decay=1.2,
        pad_enabled=True,
        pad_gain=0.05,
    ),
    "legacy_ping": SoundPaletteSpec(
        palette="legacy_ping",
        scale="pentatonic_major",
        root="C4",
        octaves=3,
        reverb_wet=0.0,
        pad_enabled=True,
        pad_gain=0.08,
    ),
}

# Add normalized aliases without spaces/hyphens for CLI convenience
PRESET_CONFIGS["glass+whole_tone"] = PRESET_CONFIGS["glass+whole-tone"]
PRESET_CONFIGS["marimba+minor_reverb"] = PRESET_CONFIGS["marimba+minor with reverb"]
PRESET_CONFIGS["pluck+major_grid"] = PRESET_CONFIGS["pluck+major with grid quantization"]
