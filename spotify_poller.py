"""Background QThread that polls the Spotify Web API for playback state."""
from __future__ import annotations

import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from PyQt6.QtCore import QThread, pyqtSignal

import config
import credentials


class TrackInfo:
    """Snapshot of a single Spotify playback state."""
    __slots__ = ("track_id", "track_name", "artist_name", "album_name",
                 "progress_ms", "duration_ms", "is_playing",
                 "_fetched_at")

    def __init__(self, track_id: str, track_name: str, artist_name: str,
                 album_name: str, progress_ms: int, duration_ms: int,
                 is_playing: bool) -> None:
        self.track_id    = track_id
        self.track_name  = track_name
        self.artist_name = artist_name
        self.album_name  = album_name
        self.progress_ms = progress_ms
        self.duration_ms = duration_ms
        self.is_playing  = is_playing
        self._fetched_at = time.monotonic()

    def interpolated_progress_ms(self) -> int:
        """Add wall-clock elapsed time to the last known progress."""
        if not self.is_playing:
            return self.progress_ms
        elapsed = int((time.monotonic() - self._fetched_at) * 1000)
        return min(self.progress_ms + elapsed, self.duration_ms)


class SpotifyPoller(QThread):
    """Emits signals as Spotify playback changes.

    Runs on its own thread so the Qt event loop is never blocked.
    """

    # A new / different track started playing
    track_changed = pyqtSignal(object)       # TrackInfo
    # Playback position updated (same track)
    position_updated = pyqtSignal(object)    # TrackInfo
    # Playback paused or nothing is playing
    playback_stopped = pyqtSignal()
    # Unrecoverable auth / connection error
    auth_error = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running       = False
        self._sp: spotipy.Spotify | None = None
        self._last_track_id: str | None  = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._running = False

    # ── QThread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=credentials.get_client_id(),
                client_secret=credentials.get_client_secret(),
                redirect_uri=config.SPOTIFY_REDIRECT_URI,
                scope=config.SPOTIFY_SCOPES,
                open_browser=True,
                cache_path=".spotify_cache",
            ))
        except Exception as exc:
            self.auth_error.emit(str(exc))
            return

        self._running = True
        interval_s = config.POLL_INTERVAL_MS / 1000.0

        while self._running:
            self._poll_once()
            time.sleep(interval_s)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _poll_once(self) -> None:
        try:
            data = self._sp.current_playback()
        except spotipy.exceptions.SpotifyException as exc:
            # 401 typically means token expired; spotipy auto-refreshes,
            # so a transient error here is usually recoverable — just skip.
            if exc.http_status == 401:
                self.auth_error.emit(f"Auth error: {exc}")
            return
        except Exception:
            return   # Network blip — ignore and retry next cycle

        if not data or not data.get("item"):
            if self._last_track_id is not None:
                self._last_track_id = None
                self.playback_stopped.emit()
            return

        item    = data["item"]
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        info    = TrackInfo(
            track_id    = item["id"],
            track_name  = item["name"],
            artist_name = artists,
            album_name  = item.get("album", {}).get("name", ""),
            progress_ms = data.get("progress_ms") or 0,
            duration_ms = item.get("duration_ms") or 0,
            is_playing  = data.get("is_playing", False),
        )

        if info.track_id != self._last_track_id:
            self._last_track_id = info.track_id
            self.track_changed.emit(info)
        else:
            self.position_updated.emit(info)
