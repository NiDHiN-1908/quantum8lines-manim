"""
Environment variable support with .env loading for Quantum8Lines.
Follows SPEC.md Section 21.1 and Milestone M5a.
"""

from pathlib import Path
import os
from typing import Optional, Dict


def load_dotenv(dotenv_path: Optional[str | Path] = None) -> Dict[str, str]:
    """
    Parses an ignored .env file and sets values in os.environ if not already set.
    Never overwrites existing environment variables.
    """
    path = Path(dotenv_path or ".env")
    loaded: Dict[str, str] = {}
    if not path.is_file():
        return loaded

    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return loaded

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        loaded[key] = value
        if key not in os.environ:
            os.environ[key] = value

    return loaded
