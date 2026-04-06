"""Orchestrates Spotify polling, lyrics fetching, and display updates."""
from __future__ import annotations

import bisect

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from lrc_parser import LyricLine
from lyrics_fetcher import LyricsFetcher
from spotify_poller import SpotifyPoller, TrackInfo
import config


class AppController(QObject):
    # ── Signals consumed by the overlay ────────────────────────────────────────
    display_update   = pyqtSignal(list, int)    # lines: list[str], current_idx: int
    track_info_ready = pyqtSignal(str, str)     # track_name, artist_name
    status_changed   = pyqtSignal(str)          # human-readable status line
    hide_overlay     = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._lyric_lines:  list[LyricLine]    = []
        self._is_synced:    bool               = False
        self._current_info: TrackInfo | None   = None
        self._fetcher:      LyricsFetcher | None = None

        # ── Spotify polling thread ─────────────────────────────────────────────
        self._poller = SpotifyPoller(self)
        self._poller.track_changed.connect(self._on_track_changed)
        self._poller.position_updated.connect(self._on_position_updated)
        self._poller.playback_stopped.connect(self._on_playback_stopped)
        self._poller.auth_error.connect(lambda e: self.status_changed.emit(f"Auth error: {e}"))

        # ── Sync timer (fires every 200 ms for smooth lyric transitions) ───────
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(200)
        self._sync_timer.timeout.connect(self._tick_sync)

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.status_changed.emit("Connecting to Spotify…")
        self._poller.start()
        self._sync_timer.start()

    def stop(self) -> None:
        self._sync_timer.stop()
        self._poller.stop()
        self._poller.wait(3000)

    def restart_poller(self) -> None:
        """Stop the current poller and start a fresh one (e.g. after credentials change)."""
        import os
        self._sync_timer.stop()
        self._poller.stop()
        self._poller.wait(3000)

        # Remove cached token so spotipy re-authenticates with the new credentials
        if os.path.exists(".spotify_cache"):
            os.remove(".spotify_cache")

        self._lyric_lines  = []
        self._current_info = None

        self._poller = SpotifyPoller(self)
        self._poller.track_changed.connect(self._on_track_changed)
        self._poller.position_updated.connect(self._on_position_updated)
        self._poller.playback_stopped.connect(self._on_playback_stopped)
        self._poller.auth_error.connect(lambda e: self.status_changed.emit(f"Auth error: {e}"))

        self.status_changed.emit("Reconnecting to Spotify\u2026")
        self._poller.start()
        self._sync_timer.start()

    # ── Spotify poller slots ───────────────────────────────────────────────────

    def _on_track_changed(self, info: TrackInfo) -> None:
        self._current_info = info
        self._lyric_lines  = []
        self._is_synced    = False

        self.track_info_ready.emit(info.track_name, info.artist_name)
        self.status_changed.emit(f'Fetching lyrics for \u201c{info.track_name}\u201d\u2026')

        # Cancel any in-flight fetcher
        if self._fetcher and self._fetcher.isRunning():
            self._fetcher.terminate()
            self._fetcher.wait(1000)

        self._fetcher = LyricsFetcher(
            track_name  = info.track_name,
            artist_name = info.artist_name,
            album_name  = info.album_name,
            duration_s  = info.duration_ms / 1000.0,
            parent      = self,
        )
        self._fetcher.lyrics_ready.connect(self._on_lyrics_ready)
        self._fetcher.lyrics_not_found.connect(self._on_lyrics_not_found)
        self._fetcher.start()

    def _on_position_updated(self, info: TrackInfo) -> None:
        self._current_info = info

    def _on_playback_stopped(self) -> None:
        self._current_info = None
        self._lyric_lines  = []
        self.hide_overlay.emit()
        self.status_changed.emit("Nothing playing")

    # ── Lyrics fetcher slots ───────────────────────────────────────────────────

    def _on_lyrics_ready(self, lines: list[LyricLine], is_synced: bool) -> None:
        self._lyric_lines = lines
        self._is_synced   = is_synced
        label = "synced" if is_synced else "plain (no timestamps)"
        self.status_changed.emit(f"Lyrics loaded ({label})")

    def _on_lyrics_not_found(self) -> None:
        self.status_changed.emit("No lyrics found for this track")
        self.hide_overlay.emit()

    # ── Sync timer ─────────────────────────────────────────────────────────────

    def _tick_sync(self) -> None:
        if not self._current_info or not self._lyric_lines:
            return

        pos_ms = self._current_info.interpolated_progress_ms()
        if self._is_synced:
            cur_idx = self._find_line_idx(pos_ms)
        else:
            # No timestamps — estimate position from playback percentage
            dur_ms = max(self._current_info.duration_ms, 1)
            pct    = min(pos_ms / dur_ms, 1.0)
            cur_idx = int(pct * len(self._lyric_lines))
            cur_idx = min(cur_idx, len(self._lyric_lines) - 1)

        texts = [l.text for l in self._lyric_lines]
        self.display_update.emit(texts, cur_idx)

    def _find_line_idx(self, position_ms: int) -> int:
        """Return the index of the last lyric whose timestamp <= position_ms."""
        if not self._lyric_lines:
            return -1
        timestamps = [l.timestamp_ms for l in self._lyric_lines]
        idx = bisect.bisect_right(timestamps, position_ms) - 1
        return max(idx, 0)
