"""Capture system audio via WASAPI loopback and emit log-scaled FFT bands."""
from __future__ import annotations

import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

_N_BANDS    = 48
_FFT_SIZE   = 2048
_SAMPLERATE = 44100
_BLOCKSIZE  = 1024
_FREQ_MIN   = 40
_FREQ_MAX   = 16000

# Pre-compute log-spaced frequency bin edges once at import time
_FREQS = np.fft.rfftfreq(_FFT_SIZE, 1.0 / _SAMPLERATE)
_EDGES = np.logspace(np.log10(_FREQ_MIN), np.log10(_FREQ_MAX), _N_BANDS + 1)
_BAND_SLICES: list[tuple[int, int]] = []
for _i in range(_N_BANDS):
    lo = int(np.searchsorted(_FREQS, _EDGES[_i]))
    hi = int(np.searchsorted(_FREQS, _EDGES[_i + 1]))
    _BAND_SLICES.append((lo, max(hi, lo + 1)))


# ── Device discovery ───────────────────────────────────────────────────────────

def list_capture_devices() -> list[dict]:
    """Return all input devices that can capture system audio, best first.

    Each entry: {"index": int, "name": str, "channels": int}
    Priority: Stereo Mix / loopback-named devices first, then other inputs.
    """
    try:
        import sounddevice as sd
        hostapis = sd.query_hostapis()
        results: list[dict] = []
        others:  list[dict] = []

        _SYSTEM_AUDIO_KW = ("stereo mix", "what u hear", "wave out mix",
                            "loopback", "mixage stéréo")

        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] < 1:
                continue
            name_lower = d["name"].lower()
            entry = {
                "index":    i,
                "name":     d["name"],
                "channels": min(d["max_input_channels"], 2),
            }
            if any(kw in name_lower for kw in _SYSTEM_AUDIO_KW):
                results.append(entry)
            else:
                others.append(entry)

        return results + others
    except Exception:
        return []


def default_capture_device() -> dict | None:
    """Return the best available system-audio capture device."""
    candidates = list_capture_devices()
    # Prefer devices whose name contains a system-audio keyword
    _SYSTEM_AUDIO_KW = ("stereo mix", "what u hear", "wave out mix",
                        "loopback", "mixage stéréo")
    for c in candidates:
        if any(kw in c["name"].lower() for kw in _SYSTEM_AUDIO_KW):
            return c
    return candidates[0] if candidates else None


# ── Capture thread ─────────────────────────────────────────────────────────────

class AudioCapture(QThread):
    """Captures system audio and emits normalised band amplitudes at ~30 fps."""

    bands_ready   = pyqtSignal(list)   # list[float] length == _N_BANDS
    capture_error = pyqtSignal(str)

    def __init__(self, device: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._device   = device   # None = auto-detect each run
        self._running  = False
        self._peak     = 1.0
        self._smoothed = [0.0] * _N_BANDS

    @property
    def n_bands(self) -> int:
        return _N_BANDS

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            self.capture_error.emit(
                "sounddevice not installed — run: pip install sounddevice numpy"
            )
            return

        dev = self._device or default_capture_device()
        if dev is None:
            self.capture_error.emit(
                "No audio capture device found. "
                "Ensure a WASAPI output device or Stereo Mix is available."
            )
            return

        self._running  = True
        self._peak     = 1.0
        self._smoothed = [0.0] * _N_BANDS

        window    = np.hanning(_FFT_SIZE)
        buf       = np.zeros(_FFT_SIZE, dtype=np.float32)
        write_pos = 0
        interval  = 1.0 / 30
        last_emit = 0.0

        def _callback(indata, frames, _t, _status):
            nonlocal write_pos
            mono = indata.mean(axis=1).astype(np.float32)
            n    = len(mono)
            if write_pos + n <= _FFT_SIZE:
                buf[write_pos:write_pos + n] = mono
                write_pos += n
            else:
                buf[:-n] = buf[n:]
                buf[-n:] = mono
                write_pos = _FFT_SIZE

        try:
            with sd.InputStream(
                device    = dev["index"],
                samplerate= _SAMPLERATE,
                blocksize = _BLOCKSIZE,
                channels  = dev["channels"],
                callback  = _callback,
                dtype     = "float32",
            ):
                while self._running:
                    now = time.monotonic()
                    if now - last_emit >= interval:
                        last_emit = now
                        self._process(buf * window)
                    time.sleep(0.005)

        except Exception as exc:
            self.capture_error.emit(
                f"Audio capture failed ({dev['name']}): {exc}"
            )

    def _process(self, frame: np.ndarray) -> None:
        spectrum = np.abs(np.fft.rfft(frame))
        raw = np.array(
            [float(np.max(spectrum[lo:hi])) for lo, hi in _BAND_SLICES],
            dtype=float,
        )

        peak = float(raw.max()) if raw.max() > 0 else 1e-6
        self._peak = peak if peak > self._peak else max(self._peak * 0.9995, 1e-6)

        normalised = np.clip(raw / self._peak, 0.0, 1.0)
        for i, v in enumerate(normalised):
            prev = self._smoothed[i]
            self._smoothed[i] = float(v if v > prev else prev * 0.78)

        self.bands_ready.emit(list(self._smoothed))
