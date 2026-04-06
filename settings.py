"""Persist overlay appearance settings to settings.json."""
from __future__ import annotations

import json
from pathlib import Path
from PyQt6.QtGui import QColor

_FILE = Path(__file__).parent / "settings.json"

_DEFAULTS: dict = {
    "bg_alpha":     175,
    "font_family":  "Segoe UI",
    "font_size":    22,
    "font_small":   16,
    "n_before":     2,
    "n_after":      2,
    "font_color":   "#ffffff",
    "title_color":  "#1db954",
    "vis_enabled":  True,
    "vis_color":    "#1db954",
}


def load() -> dict:
    if _FILE.exists():
        try:
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            # Fill any keys missing from older saves with defaults
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(data: dict) -> None:
    # Serialise QColor values to hex strings before writing
    serialisable = {}
    for k, v in data.items():
        serialisable[k] = v.name() if isinstance(v, QColor) else v
    _FILE.write_text(
        json.dumps(serialisable, indent=2), encoding="utf-8"
    )


def color(value: str) -> QColor:
    """Parse a hex colour string from settings into a QColor."""
    return QColor(value)
