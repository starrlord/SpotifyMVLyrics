"""One-shot QThread that fetches synced lyrics from lrclib.net."""
from __future__ import annotations

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from lrc_parser import LyricLine, parse_lrc, plain_to_lines

_BASE_URL = "https://lrclib.net/api"
_TIMEOUT  = 8  # seconds


class LyricsFetcher(QThread):
    """Fetches lyrics for one track, then exits.

    Prefer synced (LRC) lyrics; fall back to plain text if unavailable.
    """

    lyrics_ready     = pyqtSignal(list, bool)   # list[LyricLine], is_synced
    lyrics_not_found = pyqtSignal()

    def __init__(self, track_name: str, artist_name: str,
                 album_name: str, duration_s: float,
                 parent=None) -> None:
        super().__init__(parent)
        self._track_name  = track_name
        self._artist_name = artist_name
        self._album_name  = album_name
        self._duration_s  = duration_s

    # ── QThread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        lines, synced = self._fetch()
        if lines:
            self.lyrics_ready.emit(lines, synced)
        else:
            self.lyrics_not_found.emit()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _fetch(self) -> tuple[list[LyricLine], bool]:
        # Try exact match first (faster)
        try:
            resp = requests.get(
                f"{_BASE_URL}/get",
                params={
                    "artist_name": self._artist_name,
                    "track_name":  self._track_name,
                    "album_name":  self._album_name,
                    "duration":    int(self._duration_s),
                },
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                result = self._extract(data)
                if result[0]:
                    return result
        except Exception:
            pass

        # Fall back to search
        try:
            resp = requests.get(
                f"{_BASE_URL}/search",
                params={"q": f"{self._artist_name} {self._track_name}"},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    return self._extract(results[0])
        except Exception:
            pass

        return [], False

    @staticmethod
    def _extract(data: dict) -> tuple[list[LyricLine], bool]:
        synced = data.get("syncedLyrics")
        if synced:
            parsed = parse_lrc(synced)
            if parsed:
                return parsed, True
        plain = data.get("plainLyrics")
        if plain:
            return plain_to_lines(plain), False
        return [], False
