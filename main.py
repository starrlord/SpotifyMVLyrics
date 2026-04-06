"""Entry point: wires controller and overlay, starts the Qt event loop."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction, QPainter
from PyQt6.QtCore import Qt

from controller    import AppController
from overlay       import LyricsOverlay
from audio_capture import AudioCapture
import credentials


def _make_tray_icon(app: QApplication) -> QSystemTrayIcon:
    px = QPixmap(16, 16)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#1DB954"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, 14, 14)
    p.end()

    tray = QSystemTrayIcon(QIcon(px), app)
    menu = QMenu()
    menu.setStyleSheet("""
        QMenu { background:#2a2a2a; color:#e0e0e0; border:1px solid #555; border-radius:6px; }
        QMenu::item:selected { background:#444; }
    """)
    quit_act = QAction("Quit Lyrics Overlay")
    quit_act.triggered.connect(app.quit)
    menu.addAction(quit_act)
    tray.setContextMenu(menu)
    tray.setToolTip("Spotify Lyrics Overlay")
    tray.show()
    return tray


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray    = _make_tray_icon(app)
    overlay = LyricsOverlay()
    ctrl    = AppController()

    # Wire controller → overlay
    ctrl.display_update.connect(overlay.update_display)
    ctrl.track_info_ready.connect(overlay.update_track_info)
    ctrl.status_changed.connect(overlay.update_status)
    ctrl.hide_overlay.connect(overlay.hide_for_no_lyrics)

    # Wire credentials saved → restart poller
    overlay.credentials_saved.connect(ctrl.restart_poller)

    # Tray left-click toggles visibility
    def _tray_clicked(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if overlay.isVisible():
                overlay._hide_to_tray()
            else:
                overlay.show_from_tray()

    tray.activated.connect(_tray_clicked)

    # ── Audio visualizer ──────────────────────────────────────────────────────
    capture = AudioCapture()
    capture.bands_ready.connect(overlay.update_visualizer)
    capture.capture_error.connect(lambda e: overlay.update_status(f"Visualizer: {e}"))
    capture.start()

    def _restart_capture(device: dict | None) -> None:
        capture.stop()
        capture.wait(2000)
        capture._device   = device
        capture._running  = False
        capture.bands_ready.connect(overlay.update_visualizer)
        capture.start()

    overlay.capture_device_changed.connect(_restart_capture)

    overlay.show()

    if credentials.are_set():
        ctrl.start()
    else:
        overlay.update_status(
            "No Spotify credentials set.\nRight-click \u2192 Spotify Credentials\u2026"
        )
        overlay.credentials_saved.connect(ctrl.start, Qt.ConnectionType.SingleShotConnection)

    ret = app.exec()
    ctrl.stop()
    capture.stop()
    capture.wait(2000)
    return ret


if __name__ == "__main__":
    sys.exit(main())
