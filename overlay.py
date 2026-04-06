"""Transparent, always-on-top lyrics overlay widget."""
from __future__ import annotations

from PyQt6.QtCore    import Qt, QPoint, QRect, QRectF, pyqtSignal
from PyQt6.QtGui     import QColor, QFont, QPainter, QBrush, QAction, QActionGroup
from PyQt6.QtWidgets import (QWidget, QApplication, QMenu, QSizeGrip,
                              QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QLabel, QLineEdit, QPushButton, QDialogButtonBox)

import config
import credentials

_HEADER_H  = 34   # px reserved for track title at top
_GRIP_SIZE = 22   # resize grip square

_MENU_QSS = """
QMenu {
    background: #1a1a1a;
    color: #e8e8e8;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    padding: 4px;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMenu::item {
    padding: 5px 22px 5px 10px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #2d2d2d;
}
QMenu::item:disabled {
    color: #555;
}
QMenu::indicator {
    width: 14px;
    height: 14px;
    margin-left: 4px;
}
QMenu::indicator:checked {
    image: none;
    background: #1DB954;
    border-radius: 3px;
    border: 1px solid #1DB954;
}
QMenu::indicator:unchecked {
    background: transparent;
    border: 1px solid #555;
    border-radius: 3px;
}
QMenu::separator {
    height: 1px;
    background: #333;
    margin: 4px 6px;
}
QMenu::right-arrow {
    width: 8px;
    height: 8px;
}
"""


class CredentialsDialog(QDialog):
    """Dark-themed dialog for entering Spotify API credentials."""

    _QSS = """
        QDialog { background: #1a1a1a; }
        QLabel  { color: #c8c8c8; font-family: "Segoe UI"; font-size: 13px; }
        QLabel#heading {
            color: #ffffff; font-size: 14px; font-weight: bold;
        }
        QLabel#hint {
            color: #888; font-size: 11px;
        }
        QLineEdit {
            background: #2a2a2a; color: #e8e8e8;
            border: 1px solid #3a3a3a; border-radius: 5px;
            padding: 6px 8px; font-family: "Segoe UI"; font-size: 13px;
        }
        QLineEdit:focus { border-color: #1DB954; }
        QPushButton {
            background: #2a2a2a; color: #e8e8e8;
            border: 1px solid #3a3a3a; border-radius: 5px;
            padding: 6px 18px; font-family: "Segoe UI"; font-size: 13px;
        }
        QPushButton:hover   { background: #333; border-color: #555; }
        QPushButton#save    { background: #1DB954; color: #000; border-color: #1DB954; }
        QPushButton#save:hover { background: #1ed760; }
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Spotify Credentials")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedWidth(440)
        self.setStyleSheet(self._QSS)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        heading = QLabel("Spotify Developer Credentials")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        hint = QLabel(
            "Create a free app at developer.spotify.com \u2192 Dashboard,\n"
            "then add  http://127.0.0.1:8888/callback  as a Redirect URI."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._id_input = QLineEdit(credentials.get_client_id())
        self._id_input.setPlaceholderText("e.g. 6b16b513…")
        form.addRow("Client ID:", self._id_input)

        self._secret_input = QLineEdit(credentials.get_client_secret())
        self._secret_input.setPlaceholderText("e.g. a953e044…")
        self._secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client Secret:", self._secret_input)

        layout.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        cid    = self._id_input.text().strip()
        secret = self._secret_input.text().strip()
        if cid and secret:
            credentials.save(cid, secret)
            self.accept()

    def get_values(self) -> tuple[str, str]:
        return self._id_input.text().strip(), self._secret_input.text().strip()


class LyricsOverlay(QWidget):
    """Frameless, translucent overlay that renders synced lyrics.

    • Left-drag anywhere (except bottom-right grip) to move.
    • Drag the bottom-right corner to resize.
    • Right-click for the full configuration menu.
    """

    credentials_saved = pyqtSignal()   # emitted after new credentials are written

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._lines:       list[str]     = []
        self._current_idx: int           = -1
        self._drag_pos:    QPoint | None = None
        self._track_name:  str           = ""
        self._artist_name: str           = ""
        self._status:      str           = "Waiting for Spotify\u2026"

        # ── Live config (all editable via right-click menu) ────────────────────
        self._bg_alpha    : int = config.OVERLAY_BG_ALPHA
        self._font_family : str = config.OVERLAY_FONT_FAMILY
        self._font_size   : int = config.OVERLAY_FONT_SIZE_PX
        self._font_small  : int = config.OVERLAY_FONT_SMALL_PX
        self._n_before    : int = config.OVERLAY_LINES_BEFORE
        self._n_after     : int = config.OVERLAY_LINES_AFTER

        self._setup_window()

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(_GRIP_SIZE, _GRIP_SIZE)
        self._grip.setStyleSheet("background: transparent;")
        self._grip.setCursor(Qt.CursorShape.SizeFDiagCursor)

    # ── Window setup ───────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(380, 140)
        self.resize(config.OVERLAY_WIDTH, config.OVERLAY_HEIGHT)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width() - config.OVERLAY_WIDTH) // 2,
            screen.height() - config.OVERLAY_HEIGHT - 80,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grip.move(self.width() - _GRIP_SIZE, self.height() - _GRIP_SIZE)

    # ── Public slots ───────────────────────────────────────────────────────────

    def update_display(self, lines: list[str], current_idx: int) -> None:
        self._lines       = lines
        self._current_idx = current_idx
        if not self.isVisible():
            self.show()
        self.update()

    def update_track_info(self, track_name: str, artist_name: str) -> None:
        self._track_name  = track_name
        self._artist_name = artist_name
        self.update()

    def update_status(self, status: str) -> None:
        self._status = status
        self.update()

    def hide_for_no_lyrics(self) -> None:
        self._lines       = []
        self._current_idx = -1
        self.hide()

    # ── Painting ───────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        w, h   = self.width(), self.height()
        margin = 18

        # Background
        painter.setBrush(QBrush(QColor(10, 10, 10, self._bg_alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, w, h), 14, 14)

        # Track header
        if self._track_name:
            painter.setFont(QFont(self._font_family, 10, QFont.Weight.Bold))
            painter.setPen(QColor(29, 185, 84, 230))
            header = f"{self._track_name}  \u2013  {self._artist_name}"
            header = painter.fontMetrics().elidedText(
                header, Qt.TextElideMode.ElideRight, w - margin * 2)
            painter.drawText(
                QRect(margin, 6, w - margin * 2, _HEADER_H - 6),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                header,
            )

        # Separator
        painter.setPen(QColor(255, 255, 255, 18))
        painter.drawLine(margin, _HEADER_H, w - margin, _HEADER_H)
        painter.setPen(Qt.PenStyle.NoPen)

        if not self._lines:
            self._draw_status(painter, w, h, margin)
        else:
            self._draw_lyrics(painter, w, h, margin)

        self._draw_grip_hint(painter, w, h)

    def _draw_lyrics(self, painter: QPainter, w: int, h: int, margin: int) -> None:
        cur = self._current_idx

        start = max(0, cur - self._n_before)
        end   = min(len(self._lines), cur + self._n_after + 1)
        total_slots = self._n_before + 1 + self._n_after
        if end - start < total_slots:
            if start == 0:
                end   = min(len(self._lines), total_slots)
            else:
                start = max(0, end - total_slots)

        indices = list(range(start, end))
        if not indices:
            self._draw_status(painter, w, h, margin)
            return

        top    = _HEADER_H + 4
        avail  = h - top - 10
        line_h = max(avail // len(indices), 28)

        for slot, idx in enumerate(indices):
            is_current = (idx == cur)
            distance   = abs(idx - cur)

            rect_y = top + slot * line_h
            rect   = QRect(margin, rect_y, w - margin * 2, line_h)

            if is_current:
                painter.setBrush(QBrush(QColor(255, 255, 255, 22)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    QRectF(margin - 6, rect_y + 2, w - (margin - 6) * 2, line_h - 4),
                    6, 6,
                )

            if is_current:
                font_size, weight, alpha = self._font_size, QFont.Weight.Bold, 255
            elif distance == 1:
                font_size, weight, alpha = self._font_small, QFont.Weight.Normal, 150
            else:
                font_size, weight, alpha = max(self._font_small - 3, 10), QFont.Weight.Normal, 85

            painter.setFont(QFont(self._font_family, font_size, weight))
            text  = painter.fontMetrics().elidedText(
                self._lines[idx], Qt.TextElideMode.ElideRight, rect.width())
            align = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

            painter.setPen(QColor(0, 0, 0, min(alpha + 30, 220)))
            painter.drawText(QRect(rect.x() + 1, rect.y() + 1, rect.width(), rect.height()),
                             align, text)
            painter.setPen(QColor(255, 255, 255, alpha))
            painter.drawText(rect, align, text)

    def _draw_status(self, painter: QPainter, w: int, h: int, margin: int) -> None:
        painter.setFont(QFont(self._font_family, 13))
        painter.setPen(QColor(140, 140, 140, 180))
        painter.drawText(
            QRect(margin, _HEADER_H, w - margin * 2, h - _HEADER_H),
            int(Qt.AlignmentFlag.AlignCenter),
            self._status,
        )

    def _draw_grip_hint(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QColor(255, 255, 255, 45))
        dot, gap = 2, 5
        for i in range(3):
            for j in range(3 - i):
                painter.drawEllipse(w - _GRIP_SIZE + i * gap + 4,
                                    h - _GRIP_SIZE + (2 - j) * gap + 4, dot, dot)

    # ── Drag ───────────────────────────────────────────────────────────────────

    def _in_grip(self, pos: QPoint) -> bool:
        return pos.x() >= self.width() - _GRIP_SIZE and pos.y() >= self.height() - _GRIP_SIZE

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._in_grip(event.pos()):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None

    # ── Context / config menu ──────────────────────────────────────────────────

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_QSS)

        # ── Section label (disabled, acts as heading) ──────────────────────────
        def _section(parent: QMenu, label: str) -> None:
            a = QAction(label, parent)
            a.setEnabled(False)
            parent.addAction(a)

        # ── Appearance ────────────────────────────────────────────────────────
        _section(menu, "  Appearance")

        opacity_menu = menu.addMenu("  Opacity")
        opacity_menu.setStyleSheet(_MENU_QSS)
        grp = QActionGroup(opacity_menu)
        grp.setExclusive(True)
        for pct in (100, 85, 70, 55, 40):
            a = QAction(f"{pct}%", opacity_menu)
            a.setCheckable(True)
            a.setChecked(round(self._bg_alpha / 255 * 100 / 5) * 5 == pct)
            a.triggered.connect(lambda _, p=pct: self._set("_bg_alpha", int(255 * p / 100)))
            grp.addAction(a)
            opacity_menu.addAction(a)

        font_size_menu = menu.addMenu("  Font Size")
        font_size_menu.setStyleSheet(_MENU_QSS)
        grp2 = QActionGroup(font_size_menu)
        grp2.setExclusive(True)
        for label, size in (("Small", 16), ("Medium", 20), ("Large", 24), ("X-Large", 30)):
            a = QAction(label, font_size_menu)
            a.setCheckable(True)
            a.setChecked(self._font_size == size)
            a.triggered.connect(lambda _, s=size: (
                self._set("_font_size", s),
                self._set("_font_small", max(s - 6, 10)),
            ))
            grp2.addAction(a)
            font_size_menu.addAction(a)

        font_menu = menu.addMenu("  Font")
        font_menu.setStyleSheet(_MENU_QSS)
        grp3 = QActionGroup(font_menu)
        grp3.setExclusive(True)
        for fname in ("Segoe UI", "Arial", "Calibri", "Georgia", "Consolas"):
            a = QAction(fname, font_menu)
            a.setCheckable(True)
            a.setChecked(self._font_family == fname)
            a.triggered.connect(lambda _, f=fname: self._set("_font_family", f))
            grp3.addAction(a)
            font_menu.addAction(a)

        menu.addSeparator()

        # ── Lyrics ────────────────────────────────────────────────────────────
        _section(menu, "  Lyrics")

        ctx_menu = menu.addMenu("  Context Lines")
        ctx_menu.setStyleSheet(_MENU_QSS)
        grp4 = QActionGroup(ctx_menu)
        grp4.setExclusive(True)
        for n in (1, 2, 3, 4):
            label = f"{n} line{'s' if n > 1 else ''} above & below"
            a = QAction(label, ctx_menu)
            a.setCheckable(True)
            a.setChecked(self._n_before == n)
            a.triggered.connect(lambda _, v=n: (
                self._set("_n_before", v),
                self._set("_n_after", v),
            ))
            grp4.addAction(a)
            ctx_menu.addAction(a)

        menu.addSeparator()

        # ── Spotify ───────────────────────────────────────────────────────────
        _section(menu, "  Spotify")

        creds_label = "  Spotify Credentials\u2026"
        if not credentials.are_set():
            creds_label += "  \u26a0"   # warning triangle if not yet configured
        creds_act = QAction(creds_label, menu)
        creds_act.triggered.connect(self._open_credentials_dialog)
        menu.addAction(creds_act)

        menu.addSeparator()

        # ── Window ────────────────────────────────────────────────────────────
        _section(menu, "  Window")

        reset_act = QAction("  Reset Position", menu)
        reset_act.triggered.connect(self._reset_position)
        menu.addAction(reset_act)

        menu.addSeparator()

        hide_act = QAction("  Hide to Tray", menu)
        hide_act.triggered.connect(self.hide)
        menu.addAction(hide_act)

        quit_act = QAction("  Quit", menu)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(quit_act)

        menu.exec(event.globalPos())

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _open_credentials_dialog(self) -> None:
        dlg = CredentialsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.update_status("Reconnecting to Spotify\u2026")
            self.credentials_saved.emit()

    def _set(self, attr: str, value) -> None:
        setattr(self, attr, value)
        self.update()

    def _reset_position(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2,
            screen.height() - self.height() - 80,
        )
