"""Parse LRC-format synced lyrics into (timestamp_ms, text) pairs."""
from __future__ import annotations

import re
from dataclasses import dataclass

_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{2})\.(\d{2,3})\]")


@dataclass(frozen=True)
class LyricLine:
    timestamp_ms: int
    text: str


def parse_lrc(lrc_text: str) -> list[LyricLine]:
    """Return a time-sorted list of LyricLine objects from an LRC string.

    Handles both 2-digit centisecond and 3-digit millisecond sub-second parts.
    Lines with no timestamp (e.g. ID tags) are skipped.
    Empty/instrumental lines are kept so the display can go blank naturally.
    """
    lines: list[LyricLine] = []
    for raw in lrc_text.splitlines():
        for m in _TIMESTAMP_RE.finditer(raw):
            minutes   = int(m.group(1))
            seconds   = int(m.group(2))
            subsecond = m.group(3)
            # Normalise to milliseconds
            if len(subsecond) == 2:
                ms = int(subsecond) * 10
            else:
                ms = int(subsecond)
            total_ms = (minutes * 60 + seconds) * 1000 + ms
            # Text is everything after the last timestamp tag on this line
            text = _TIMESTAMP_RE.sub("", raw).strip()
            lines.append(LyricLine(timestamp_ms=total_ms, text=text))
    lines.sort(key=lambda l: l.timestamp_ms)
    return lines


def plain_to_lines(plain_text: str) -> list[LyricLine]:
    """Wrap plain (un-timed) lyrics as LyricLine objects with timestamp 0.

    All lines share timestamp 0 so the overlay shows them sequentially
    without sync — better than nothing.
    """
    return [LyricLine(timestamp_ms=0, text=t.strip())
            for t in plain_text.splitlines() if t.strip()]
