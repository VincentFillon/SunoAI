"""
app.py — Suno AI Prompt Generator — Desktop UI (PySide6).

Entry point: python app.py
"""
from __future__ import annotations

import datetime
import difflib
import os
import sys
import threading
import webbrowser
from enum import Enum, auto

from PySide6.QtCore import (
    Qt, QThread, QTimer, QPropertyAnimation, QEasingCurve,
    Signal, QObject, QEvent,
)
from PySide6.QtGui import QFont, QShortcut, QKeySequence, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QScrollArea, QFrame,
    QStackedWidget, QSizePolicy, QDialog, QComboBox, QGridLayout,
    QProgressBar, QGraphicsOpacityEffect, QCheckBox,
)

import settings
import core
import history_index
from providers import PROVIDERS, PRICING_UPDATED_AT, LLMClient, estimate_cost

# ─────────────────────────────────────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────────────────────────────────────
BG_BASE        = "#0f0f1a"
BG_SURFACE_1   = "#16162a"
BG_SURFACE_2   = "#1e1e38"
BG_SURFACE_3   = "#252545"
ACCENT         = "#7c6af0"
ACCENT_HOVER   = "#9585f5"
ACCENT_DIM     = "#3d3570"
TEXT_PRIMARY   = "#e8e8f0"
TEXT_SECONDARY = "#8888aa"
TEXT_MUTED     = "#555570"
SUCCESS        = "#4caf6e"
WARNING_COL    = "#ffaa44"
ERROR_COL      = "#f06a6a"
LINK           = "#6ab4f0"
SIDEBAR_BG     = "#0c0c18"
SIDEBAR_ACTIVE = "#1c1c38"

HISTORY_PAGE_SIZE = 15
INTENT_MAX_CHARS  = 2000

# ─────────────────────────────────────────────────────────────────────────────
# STYLESHEET
# ─────────────────────────────────────────────────────────────────────────────
QSS = f"""
* {{ font-family: "Segoe UI", "Arial", sans-serif; }}
QMainWindow {{ background: {BG_BASE}; }}
QWidget {{ background: transparent; color: {TEXT_PRIMARY}; }}
QDialog {{ background: {BG_SURFACE_1}; }}

QScrollBar:vertical {{
    background: {BG_SURFACE_1}; width: 8px; border-radius: 4px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_SURFACE_3}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background: {BG_SURFACE_1}; height: 8px; border-radius: 4px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BG_SURFACE_3}; border-radius: 4px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

QLineEdit, QTextEdit {{
    background-color: {BG_SURFACE_2};
    border: 1px solid {BG_SURFACE_3};
    border-radius: 6px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
QTextEdit[readOnly="true"] {{ color: {TEXT_PRIMARY}; }}

QPushButton {{
    background-color: {BG_SURFACE_2};
    color: {TEXT_SECONDARY};
    border: none; border-radius: 6px;
    padding: 6px 16px; font-size: 13px;
    min-height: 30px;
}}
QPushButton:hover {{ background-color: {BG_SURFACE_3}; color: {TEXT_PRIMARY}; }}
QPushButton:pressed {{ background-color: {ACCENT_DIM}; }}
QPushButton:disabled {{
    color: #3d3d55; background-color: #14142a;
    border: 1px solid #1a1a2e;
}}

QPushButton#accent {{
    background-color: {ACCENT}; color: white; font-weight: bold;
}}
QPushButton#accent:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton#accent:disabled {{
    background-color: #2a2550; color: #5a5575; border: none;
}}

QPushButton#success {{ background-color: #2a5a2a; color: white; }}
QPushButton#success:hover {{ background-color: #3a7a3a; }}
QPushButton#success:disabled {{ background-color: #1a2a1a; color: #4a5a4a; }}

QPushButton#danger {{ background-color: #7a1a1a; color: white; }}
QPushButton#danger:hover {{ background-color: #9a2a2a; }}

QPushButton#chip {{
    background-color: {BG_SURFACE_2}; color: {TEXT_SECONDARY};
    border: 1px solid {BG_SURFACE_3}; border-radius: 14px;
    padding: 4px 12px; min-height: 26px; font-size: 12px;
}}
QPushButton#chip:hover {{ border-color: {ACCENT_DIM}; color: {TEXT_PRIMARY}; }}
QPushButton#chip:checked {{
    background-color: {ACCENT_DIM}; color: white;
    border: 1px solid {ACCENT};
}}

QProgressBar {{
    background: {BG_SURFACE_2}; border-radius: 2px;
    border: none; min-height: 4px;
}}
QProgressBar::chunk {{
    background: {ACCENT}; border-radius: 2px;
}}

QCheckBox {{ color: {TEXT_PRIMARY}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BG_SURFACE_3}; border-radius: 3px;
    background: {BG_SURFACE_2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}

QComboBox {{
    background-color: {BG_SURFACE_2}; color: {TEXT_PRIMARY};
    border: 1px solid {BG_SURFACE_3}; border-radius: 6px;
    padding: 6px 10px; min-height: 34px;
}}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE_2}; color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT_DIM};
    selection-background-color: {ACCENT};
    outline: none; padding: 2px;
}}

QStatusBar {{
    background: {BG_BASE}; color: {TEXT_SECONDARY};
    font-size: 11px; border-top: 1px solid {BG_SURFACE_2};
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# APP STATE
# ─────────────────────────────────────────────────────────────────────────────
class AppState(Enum):
    IDLE            = auto()
    ANALYZING       = auto()
    QUESTIONS_READY = auto()
    GENERATING      = auto()
    OUTPUT_READY    = auto()


# ─────────────────────────────────────────────────────────────────────────────
# WORKERS  — QObject + QThread; signals auto-queued to main thread
# ─────────────────────────────────────────────────────────────────────────────
class AnalyzeWorker(QObject):
    finished   = Signal()
    error      = Signal(str)
    status     = Signal(str)
    usage      = Signal(dict)        # per-call usage record
    rate_limit = Signal(float)       # countdown in seconds
    cancelled  = Signal()
    stopped    = Signal()            # always emitted last; drives thread teardown

    def __init__(self, client: LLMClient, session: dict):
        super().__init__()
        self._client     = client
        self._session    = session
        self._stop_event = threading.Event()

    def cancel(self):
        self._stop_event.set()

    def run(self):
        try:
            # Phase 0 is opportunistic — never blocks Phase 1
            core.run_phase0_intent(
                self._client, self._session,
                on_retry=self.status.emit,
                on_rate_limit=self.rate_limit.emit,
                on_usage=self.usage.emit,
                stop_event=self._stop_event,
            )
            core.run_phase1_analysis(
                self._client, self._session,
                on_retry=self.status.emit,
                on_rate_limit=self.rate_limit.emit,
                on_usage=self.usage.emit,
                stop_event=self._stop_event,
            )
            if self._stop_event.is_set():
                self.cancelled.emit()
            else:
                self.finished.emit()
        except core.CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.stopped.emit()


class GenerateWorker(QObject):
    finished   = Signal(str)         # filepath
    error      = Signal(str)
    status     = Signal(str)
    usage      = Signal(dict)
    rate_limit = Signal(float)
    cancelled  = Signal()
    stopped    = Signal()

    def __init__(self, client: LLMClient, session: dict):
        super().__init__()
        self._client     = client
        self._session    = session
        self._stop_event = threading.Event()

    def cancel(self):
        self._stop_event.set()

    def run(self):
        try:
            core.run_composition(
                self._client, self._session,
                on_retry=self.status.emit,
                on_rate_limit=self.rate_limit.emit,
                on_usage=self.usage.emit,
                stop_event=self._stop_event,
            )
            if self._stop_event.is_set():
                self.cancelled.emit()
            else:
                filepath = core.save_session(self._session)
                self.finished.emit(filepath)
        except core.CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.stopped.emit()


class ValidateKeyWorker(QObject):
    finished = Signal(bool, str, list)
    stopped  = Signal()

    def __init__(self, pid: str, key: str):
        super().__init__()
        self._pid = pid
        self._key = key

    def run(self):
        try:
            ok, msg = LLMClient.validate_key(self._pid, self._key)
            models  = LLMClient.list_models(self._pid, self._key) if ok else []
            self.finished.emit(ok, msg, models)
        except Exception as exc:
            self.finished.emit(False, str(exc), [])
        finally:
            self.stopped.emit()


def _launch(worker: QObject) -> QThread:
    """Move worker to a new QThread, wire teardown, start, return thread."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.stopped.connect(thread.quit)
    worker.stopped.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


# ─────────────────────────────────────────────────────────────────────────────
# SMALL HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {BG_SURFACE_2}; border: none;")
    return f


def _section_header(title: str) -> QFrame:
    f = QFrame()
    f.setStyleSheet(f"background: {BG_SURFACE_2}; border-radius: 8px;")
    lo = QHBoxLayout(f)
    lo.setContentsMargins(14, 7, 14, 7)
    lbl = QLabel(title)
    lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color: {ACCENT};")
    lo.addWidget(lbl)
    return f


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.deleteLater()


def _copy_flash(text: str, btn: QPushButton) -> None:
    QApplication.clipboard().setText(text)
    orig = btn.text()
    btn.setText("✓ Copié!")
    QTimer.singleShot(1500, lambda: btn.setText(orig))


# ─────────────────────────────────────────────────────────────────────────────
# NAV ITEM
# ─────────────────────────────────────────────────────────────────────────────
class NavItem(QWidget):
    clicked = Signal()

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)

        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self._bar = QFrame()
        self._bar.setFixedSize(3, 48)
        self._bar.setStyleSheet(f"background: {ACCENT};")
        self._bar.hide()
        lo.addWidget(self._bar)

        self._icon = QLabel(icon)
        self._icon.setFont(QFont("Segoe UI", 16))
        self._icon.setFixedWidth(52)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(self._icon)

        self._text = QLabel(label)
        self._text.setFont(QFont("Segoe UI", 13))
        lo.addWidget(self._text, 1)

        self._refresh_colors()

    def _refresh_colors(self):
        c = TEXT_PRIMARY if self._active else TEXT_SECONDARY
        self._icon.setStyleSheet(f"color: {c};")
        self._text.setStyleSheet(f"color: {c};")

    def enterEvent(self, e):
        if not self._active:
            self.setStyleSheet(
                f"NavItem {{ background: {BG_SURFACE_2}; border-radius: 8px; }}")
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._active:
            self.setStyleSheet("NavItem { background: transparent; }")
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)

    def set_active(self, active: bool):
        self._active = active
        self._bar.setVisible(active)
        self.setStyleSheet(
            f"NavItem {{ background: {SIDEBAR_ACTIVE}; border-radius: 8px; }}"
            if active else "NavItem { background: transparent; }"
        )
        self._refresh_colors()

    def set_label_visible(self, v: bool):
        self._text.setVisible(v)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
class Sidebar(QWidget):
    nav_clicked = Signal(str)

    COLLAPSED_W = 68
    EXPANDED_W  = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._items: dict[str, NavItem] = {}

        self.setFixedWidth(self.EXPANDED_W)
        self.setStyleSheet(f"Sidebar {{ background: {SIDEBAR_BG}; }}")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        # QPropertyAnimation on maximumWidth — smooth, non-blocking, Qt-native
        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_anim_done)

        self._build()

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        logo_row = QWidget()
        logo_row.setFixedHeight(56)
        lr = QHBoxLayout(logo_row)
        lr.setContentsMargins(14, 0, 8, 0)

        self._logo = QLabel("✦  SunoAI")
        self._logo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._logo.setStyleSheet(f"color: {TEXT_PRIMARY};")
        lr.addWidget(self._logo, 1)

        self._toggle = QPushButton("◀")
        self._toggle.setFixedSize(28, 28)
        self._toggle.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_SECONDARY};
                           border: none; border-radius: 4px; font-size: 11px; }}
            QPushButton:hover {{ background: {BG_SURFACE_2}; color: {TEXT_PRIMARY}; }}
        """)
        self._toggle.clicked.connect(self.toggle)
        lr.addWidget(self._toggle)

        lo.addWidget(logo_row)
        lo.addWidget(_sep())

        for pid, icon, label in [
            ("generator", "🎵", "Générateur"),
            ("history",   "🕘", "Historique"),
        ]:
            item = NavItem(icon, label)
            item.clicked.connect(lambda p=pid: self._nav_click(p))
            lo.addWidget(item)
            self._items[pid] = item

        lo.addStretch(1)

        s_item = NavItem("⚙", "Paramètres")
        s_item.clicked.connect(lambda: self._nav_click("settings"))
        lo.addWidget(s_item)
        self._items["settings"] = s_item

        lo.addWidget(_sep())

        self._chip = QLabel("—")
        self._chip.setFont(QFont("Segoe UI", 10))
        self._chip.setStyleSheet(
            f"color: {TEXT_MUTED}; padding: 4px 14px 10px 14px;")
        self._chip.setWordWrap(True)
        lo.addWidget(self._chip)

        self._items["generator"].set_active(True)

    def _nav_click(self, pid: str):
        for p, item in self._items.items():
            item.set_active(p == pid)
        self.nav_clicked.emit(pid)

    def set_active(self, pid: str):
        for p, item in self._items.items():
            item.set_active(p == pid)

    def set_provider_text(self, text: str):
        self._chip.setText(text)

    def toggle(self):
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
            cur = self.maximumWidth()
        else:
            cur = self.width()
        self._expanded = not self._expanded
        target = self.EXPANDED_W if self._expanded else self.COLLAPSED_W
        self._toggle.setText("▶" if not self._expanded else "◀")
        self.setMinimumWidth(0)
        self._anim.setStartValue(cur)
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_anim_done(self):
        w = self.EXPANDED_W if self._expanded else self.COLLAPSED_W
        self.setFixedWidth(w)
        v = self._expanded
        for item in self._items.values():
            item.set_label_visible(v)
        self._logo.setText("✦  SunoAI" if v else "✦")
        self._chip.setVisible(v)


# ─────────────────────────────────────────────────────────────────────────────
# STEPPER BAR
# ─────────────────────────────────────────────────────────────────────────────
class StepperBar(QWidget):
    STEPS = ["Input", "Analyse", "Questions", "Résultat"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)
        self._circles: list[QFrame] = []
        self._nums:    list[QLabel] = []
        self._labels:  list[QLabel] = []
        self._lines:   list[QFrame] = []
        self._compact  = False
        self._active_anim = None
        self._cost_lbl: QLabel | None = None
        self._build()

    def _build(self):
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 14, 0)
        lo.setSpacing(0)
        for i, step in enumerate(self.STEPS):
            col_w = QWidget()
            col_w.setStyleSheet("background: transparent;")
            col = QVBoxLayout(col_w)
            col.setContentsMargins(0, 0, 0, 0)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            circle = QFrame()
            circle.setFixedSize(34, 34)
            circle.setStyleSheet(
                f"background: {BG_SURFACE_2}; border-radius: 17px;")
            ci = QVBoxLayout(circle)
            ci.setContentsMargins(0, 0, 0, 0)
            num = QLabel(str(i + 1))
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            num.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
            ci.addWidget(num)
            self._circles.append(circle)
            self._nums.append(num)

            slbl = QLabel(step)
            slbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            slbl.setFont(QFont("Segoe UI", 10))
            slbl.setStyleSheet(f"color: {TEXT_MUTED};")
            self._labels.append(slbl)

            col.addWidget(circle, 0, Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(slbl,   0, Qt.AlignmentFlag.AlignHCenter)
            lo.addWidget(col_w)

            if i < len(self.STEPS) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                line.setStyleSheet(f"background: {ACCENT_DIM}; border: none;")
                self._lines.append(line)
                lo.addWidget(line, 1)

        self._cost_lbl = QLabel("")
        self._cost_lbl.setFont(QFont("Segoe UI", 11))
        self._cost_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; padding: 0 6px 0 14px;"
        )
        self._cost_lbl.setMinimumWidth(120)
        self._cost_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lo.addWidget(self._cost_lbl)

    def set_cost(self, in_tok: int, out_tok: int, cost_usd: float | None) -> None:
        if in_tok == 0 and out_tok == 0:
            self._cost_lbl.setText("")
            return
        cost_str = f"~${cost_usd:.4f}" if cost_usd is not None else "~$?"
        self._cost_lbl.setText(
            f"💸 {in_tok:,} in / {out_tok:,} out · {cost_str}"
        )

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        for lbl in self._labels:
            lbl.setVisible(not compact)

    def update_state(self, state: AppState):
        step_map = {
            AppState.IDLE:            (0, -1),
            AppState.ANALYZING:       (1,  1),
            AppState.QUESTIONS_READY: (2,  2),
            AppState.GENERATING:      (3,  3),
            AppState.OUTPUT_READY:    (3,  4),
        }
        active, done = step_map[state]
        for i in range(4):
            if i < done:
                self._circles[i].setStyleSheet(
                    f"background: {ACCENT}; border-radius: 17px;")
                self._nums[i].setText("✓")
                self._nums[i].setStyleSheet("color: white; background: transparent;")
                self._labels[i].setStyleSheet(f"color: {TEXT_SECONDARY};")
            elif i == active:
                self._circles[i].setStyleSheet(
                    f"background: {ACCENT}; border-radius: 17px;")
                self._nums[i].setText(str(i + 1))
                self._nums[i].setStyleSheet("color: white; background: transparent;")
                self._labels[i].setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: bold;")
                self._pop_circle(self._circles[i])
            else:
                self._circles[i].setStyleSheet(
                    f"background: {BG_SURFACE_2}; border-radius: 17px;")
                self._nums[i].setText(str(i + 1))
                self._nums[i].setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
                self._labels[i].setStyleSheet(f"color: {TEXT_MUTED};")
        for i, line in enumerate(self._lines):
            line.setStyleSheet(
                f"background: {ACCENT}; border: none;" if i < done
                else f"background: {ACCENT_DIM}; border: none;")

    def _pop_circle(self, circle: QFrame) -> None:
        """Subtle scale animation on the active step circle."""
        if self._active_anim and self._active_anim.state() == QPropertyAnimation.State.Running:
            self._active_anim.stop()
        anim = QPropertyAnimation(circle, b"minimumSize", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        from PySide6.QtCore import QSize as _QSize
        anim.setStartValue(_QSize(34, 34))
        anim.setKeyValueAt(0.5, _QSize(38, 38))
        anim.setEndValue(_QSize(34, 34))
        self._active_anim = anim
        anim.start()


# ─────────────────────────────────────────────────────────────────────────────
# LOADING CARD
# ─────────────────────────────────────────────────────────────────────────────
class LoadingCard(QFrame):
    """Prominent indeterminate progress card shown during ANALYZING/GENERATING.

    Replaces the tiny status-bar braille spinner with an unmissable banner.
    """
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loadingCard")
        self.setFixedHeight(74)
        self.setStyleSheet(
            f"QFrame#loadingCard {{"
            f"  background: {BG_SURFACE_1}; border-radius: 12px;"
            f"  border: 1px solid {ACCENT_DIM};"
            f"}}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 12, 18, 12)
        h.setSpacing(14)

        col = QVBoxLayout()
        col.setSpacing(6)
        self._label = QLabel("Analyse en cours…")
        self._label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        col.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)        # indeterminate
        self._bar.setFixedHeight(4)
        self._bar.setTextVisible(False)
        col.addWidget(self._bar)
        h.addLayout(col, 1)

        self._cancel_btn = QPushButton("✕  Annuler")
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.setFixedSize(110, 36)
        self._cancel_btn.clicked.connect(self.cancel_clicked.emit)
        h.addWidget(self._cancel_btn)
        self.hide()

    def set_text(self, text: str):
        self._label.setText(text)

    def show_for_phase(self, phase_label: str):
        self._label.setText(phase_label)
        self.show()


# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMIT BANNER
# ─────────────────────────────────────────────────────────────────────────────
class RateLimitBanner(QFrame):
    """Non-blocking banner with countdown + escape hatch when a 429 is detected."""
    switch_provider_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rateLimitBanner")
        self.setFixedHeight(48)
        self.setStyleSheet(
            f"QFrame#rateLimitBanner {{"
            f"  background: #3a2010; border-radius: 8px;"
            f"  border: 1px solid {WARNING_COL};"
            f"}}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 6, 14, 6)
        icon = QLabel("⏱")
        icon.setStyleSheet(f"color: {WARNING_COL}; font-size: 18px; background: transparent; border: none;")
        h.addWidget(icon)
        self._label = QLabel("Limite de débit atteinte. Reprise dans —s.")
        self._label.setStyleSheet(f"color: {WARNING_COL}; font-size: 12px; background: transparent; border: none;")
        h.addWidget(self._label, 1)
        self._switch_btn = QPushButton("Changer de fournisseur")
        self._switch_btn.setFixedHeight(30)
        self._switch_btn.clicked.connect(self.switch_provider_clicked.emit)
        h.addWidget(self._switch_btn)
        self.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._remaining = 0.0

    def start_countdown(self, seconds: float):
        self._remaining = max(1.0, float(seconds))
        self._update_label()
        self.show()
        self._timer.start()

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.hide()
            return
        self._update_label()

    def _update_label(self):
        self._label.setText(
            f"Limite de débit atteinte. Reprise dans {int(self._remaining)}s."
        )

    def dismiss(self):
        self._timer.stop()
        self.hide()


# ─────────────────────────────────────────────────────────────────────────────
# CHIP GROUP — typed question widget (single or multi select)
# ─────────────────────────────────────────────────────────────────────────────
class ChipGroup(QWidget):
    """Row of toggleable chips. value() returns the selected option(s) as a string."""

    def __init__(self, options: list[str], multi: bool = False, parent=None):
        super().__init__(parent)
        self._multi = multi
        self._buttons: list[QPushButton] = []
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 4, 0, 4)
        lo.setSpacing(6)
        for opt in options:
            btn = QPushButton(opt)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if not multi:
                btn.clicked.connect(lambda checked, b=btn: self._exclusive(b, checked))
            lo.addWidget(btn)
            self._buttons.append(btn)
        lo.addStretch(1)

    def _exclusive(self, clicked_btn: QPushButton, checked: bool):
        if not checked:
            return
        for b in self._buttons:
            if b is not clicked_btn:
                b.setChecked(False)

    def value(self) -> str:
        return ", ".join(b.text() for b in self._buttons if b.isChecked())

    def set_value(self, value: str):
        if not value:
            return
        wanted = {v.strip() for v in value.split(",") if v.strip()}
        for b in self._buttons:
            b.setChecked(b.text() in wanted)


# ─────────────────────────────────────────────────────────────────────────────
# HISTORY CARD
# ─────────────────────────────────────────────────────────────────────────────
class HistoryCard(QFrame):
    load_requested   = Signal(dict, dict)
    delete_requested = Signal(dict)

    _BTN = f"""QPushButton {{ background: {BG_SURFACE_3}; color: {TEXT_SECONDARY};
                  border: none; border-radius: 4px; font-size: 10px; padding: 3px 8px; }}
               QPushButton:hover {{ background: {ACCENT_DIM}; color: {TEXT_PRIMARY}; }}"""
    _LOAD = f"""QPushButton {{ background: {ACCENT}; color: white; border: none;
                  border-radius: 4px; font-size: 10px; font-weight: bold; padding: 3px 10px; }}
                QPushButton:hover {{ background: {ACCENT_HOVER}; }}"""

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"HistoryCard {{ background: {BG_SURFACE_1}; border-radius: 10px;"
            f" border: 1px solid {BG_SURFACE_2}; }}")
        sd, gens = entry["session_data"], entry["generations"]

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 12, 0)
        outer.setSpacing(0)

        stripe = QFrame()
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(
            f"background: {ACCENT_DIM}; border-radius: 0; border: none;")
        outer.addWidget(stripe)

        body = QWidget()
        body.setStyleSheet("background: transparent; border: none;")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(10, 10, 0, 10)
        bv.setSpacing(4)

        # ── header ──
        hdr = QWidget()
        hdr.setStyleSheet("background: transparent; border: none;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)

        left = QWidget()
        left.setStyleSheet("background: transparent; border: none;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)

        ref = (sd.get("user_intent")
               or " / ".join(filter(None, [sd.get("style",""), sd.get("artist","")]))
               or "Sans référence")
        tl = QLabel(ref)
        tl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {TEXT_PRIMARY};")
        tl.setWordWrap(True)
        lv.addWidget(tl)

        n   = len(gens)
        pid = sd.get("provider", "")
        mod = sd.get("model", "")
        meta = f"{n} génération{'s' if n > 1 else ''}"
        if pid:
            meta += f"  ·  {PROVIDERS.get(pid,{}).get('name', pid)}  ·  {mod}"
        ml = QLabel(meta)
        ml.setFont(QFont("Segoe UI", 10))
        ml.setStyleSheet(f"color: {TEXT_SECONDARY};")
        lv.addWidget(ml)
        hl.addWidget(left, 1)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ERROR_COL};"
            f" border: none; font-size: 13px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: #4a1515; }}")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(entry))
        hl.addWidget(del_btn, 0, Qt.AlignmentFlag.AlignTop)
        bv.addWidget(hdr)

        # ── generation rows ──
        for i, gen in enumerate(gens):
            bg = BG_SURFACE_2 if i % 2 == 0 else BG_SURFACE_1
            rf = QFrame()
            rf.setStyleSheet(
                f"QFrame {{ background: {bg}; border-radius: 6px; border: none; }}")
            rl = QHBoxLayout(rf)
            rl.setContentsMargins(8, 6, 8, 6)
            rl.setSpacing(8)

            gn = QLabel(f"#{gen['gen_num']}")
            gn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            gn.setStyleSheet(f"color: {ACCENT};")
            gn.setFixedWidth(30)
            gn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(gn)

            ic = QWidget()
            ic.setStyleSheet("background: transparent; border: none;")
            icv = QVBoxLayout(ic)
            icv.setContentsMargins(0, 0, 0, 0)
            icv.setSpacing(1)
            tit = QLabel(gen["title"] or "(sans titre)")
            tit.setFont(QFont("Segoe UI", 12))
            tit.setStyleSheet(f"color: {TEXT_PRIMARY};")
            icv.addWidget(tit)
            if gen.get("ts"):
                ts = QLabel(gen["ts"])
                ts.setFont(QFont("Segoe UI", 10))
                ts.setStyleSheet(f"color: {TEXT_MUTED};")
                icv.addWidget(ts)
            rl.addWidget(ic, 1)

            sb = QPushButton("📋 Style")
            sb.setFixedHeight(24)
            sb.setStyleSheet(self._BTN)
            sb.clicked.connect(
                lambda _, d=gen["style"], b=sb: _copy_flash(d, b))
            rl.addWidget(sb)

            lb = QPushButton("📋 Paroles")
            lb.setFixedHeight(24)
            lb.setStyleSheet(self._BTN)
            lb.clicked.connect(
                lambda _, d=gen["lyrics"], b=lb: _copy_flash(d, b))
            rl.addWidget(lb)

            load_b = QPushButton("Charger ▶")
            load_b.setFixedHeight(24)
            load_b.setStyleSheet(self._LOAD)
            load_b.clicked.connect(
                lambda _, g=gen, e=entry: self.load_requested.emit(e, g))
            rl.addWidget(load_b)

            bv.addWidget(rf)

        outer.addWidget(body, 1)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Suno AI Prompt Generator")
        self.resize(1060, 820)
        self.setMinimumSize(800, 620)

        self._state:               AppState     = AppState.IDLE
        self._session:             dict         = core.init_session()
        self._llm_client:          LLMClient | None = None
        self._worker_thread:       QThread | None   = None
        self._sp_thread:           QThread | None   = None
        self._current_worker:      object | None    = None
        self._cancel_returns_to:   AppState         = AppState.IDLE
        self._question_entries:    list[QLineEdit]  = []
        self._question_labels:     list[str]        = []
        self._spinner_tick:        int              = 0
        self._hist_page:           int              = 0
        self._hist_all_files:      list[str]        = []
        self._hist_filtered_files: list[str]        = []
        self._sp_selected_provider = "openai"
        self._sp_key_validated     = False
        self._sp_models:           list[str]        = []
        self._sp_spinner_dots      = 0

        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(100)
        self._spinner_timer.timeout.connect(self._tick_spinner)

        self._sp_spinner_timer = QTimer(self)
        self._sp_spinner_timer.setInterval(400)
        self._sp_spinner_timer.timeout.connect(self._sp_tick_spinner)

        self._build_ui()
        self._set_state(AppState.IDLE)
        QTimer.singleShot(150, self._check_config_on_start)
        # Reindex the history outputs in the background — no blocking.
        QTimer.singleShot(300, self._reindex_history_async)

        sc = QShortcut(QKeySequence("Ctrl+R"), self)
        sc.activated.connect(self._on_regen_shortcut)

    def _reindex_history_async(self):
        """Reindex outputs/ into history.db in a background thread."""
        def _do_reindex():
            try:
                history_index.reindex(core.OUTPUTS_DIR, core._parse_session_file)
            except Exception:
                pass

        t = threading.Thread(target=_do_reindex, daemon=True)
        t.start()

    # ── LAYOUT ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        root_w = QWidget()
        root_w.setStyleSheet(f"background: {BG_BASE};")
        self.setCentralWidget(root_w)

        hl = QHBoxLayout(root_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.nav_clicked.connect(self._switch_panel)
        hl.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {BG_BASE};")
        hl.addWidget(self._stack, 1)

        self._gen_panel      = self._build_generator_panel()
        self._hist_panel     = self._build_history_panel()
        self._settings_panel = self._build_settings_panel()
        self._stack.addWidget(self._gen_panel)
        self._stack.addWidget(self._hist_panel)
        self._stack.addWidget(self._settings_panel)

        self._status_lbl = QLabel("Prêt")
        self._status_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._spinner_lbl = QLabel("")
        self._spinner_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; min-width: 30px;")
        self.statusBar().addWidget(self._status_lbl, 1)
        self.statusBar().addPermanentWidget(self._spinner_lbl)

    def _switch_panel(self, pid: str):
        m = {"generator": self._gen_panel,
             "history":   self._hist_panel,
             "settings":  self._settings_panel}
        self._stack.setCurrentWidget(m[pid])
        if pid == "history":
            self._refresh_history()

    # ── GENERATOR PANEL ──────────────────────────────────────────────────────

    def _build_generator_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG_BASE};")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)

        # Stepper inside a small top container with padding
        stepper_wrap = QWidget()
        stepper_wrap.setStyleSheet(f"background: {BG_BASE};")
        sw = QVBoxLayout(stepper_wrap)
        sw.setContentsMargins(16, 10, 16, 8)
        sw.setSpacing(6)
        self._stepper = StepperBar()
        sw.addWidget(self._stepper)
        # Rate limit banner (initially hidden)
        self._rate_limit_banner = RateLimitBanner()
        self._rate_limit_banner.switch_provider_clicked.connect(
            lambda: self._switch_panel("settings"))
        sw.addWidget(self._rate_limit_banner)
        pv.addWidget(stepper_wrap)
        pv.addWidget(_sep())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background: {BG_BASE};")
        cv = QVBoxLayout(content)
        cv.setContentsMargins(16, 16, 16, 16)
        cv.setSpacing(8)
        cv.addWidget(self._build_step1())
        # Loading card sits between input and output — always visible spot
        self._loading_card = LoadingCard()
        self._loading_card.cancel_clicked.connect(self._on_cancel)
        cv.addWidget(self._loading_card)
        cv.addWidget(self._build_step2())
        cv.addWidget(self._build_step3())
        cv.addWidget(self._build_step4())
        cv.addStretch(1)
        scroll.setWidget(content)
        pv.addWidget(scroll, 1)
        return panel

    def _build_step1(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            f"QFrame {{ background: {BG_SURFACE_1}; border-radius: 12px; }}")
        self._step1_frame = f
        v = QVBoxLayout(f)
        v.setContentsMargins(12, 12, 12, 16)
        v.setSpacing(8)

        v.addWidget(_section_header("ÉTAPE 1 — DESCRIPTION"))

        desc = QLabel("Décrivez librement ce que vous souhaitez créer :")
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px;")
        v.addWidget(desc)

        self._intent_box = QTextEdit()
        self._intent_box.setFixedHeight(110)
        self._intent_box.setPlaceholderText(
            "Ex : Metal progressif et jazz manouche, paroles en français sur l'exil"
            " · Techno hypnotique 140 BPM · Pop mélancolique années 80")
        self._intent_box.setToolTip(
            "Plus c'est précis, meilleur sera le résultat.\n"
            "Mentionnez : genre/sous-genre, ambiance, instruments,\n"
            "langue des paroles, époque, énergie attendue."
        )
        self._intent_box.textChanged.connect(self._update_char_count)
        self._intent_box.installEventFilter(self)
        v.addWidget(self._intent_box)

        # Example chips — one-click prompts for first-time users
        examples_w = QWidget()
        examples_w.setStyleSheet("background: transparent;")
        ex_lo = QHBoxLayout(examples_w)
        ex_lo.setContentsMargins(0, 2, 0, 2)
        ex_lo.setSpacing(6)
        intro = QLabel("Essayez :")
        intro.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        ex_lo.addWidget(intro)
        examples = [
            "Metal progressif en français, riffs palm-muted downtuned, refrains anthémiques",
            "Techno minimale hypnotique 132 BPM, kick relentless, sans voix",
            "Pop mélancolique années 80, synthés analogiques, voix féminine douce",
        ]
        for ex in examples:
            btn = QPushButton(ex if len(ex) <= 40 else ex[:37] + "…")
            btn.setObjectName("chip")
            btn.setToolTip(ex)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=ex: self._intent_box.setPlainText(t))
            ex_lo.addWidget(btn)
        ex_lo.addStretch(1)
        v.addWidget(examples_w)

        cr = QHBoxLayout()
        self._char_lbl = QLabel(f"0 / {INTENT_MAX_CHARS}")
        self._char_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        cr.addStretch(1)
        cr.addWidget(self._char_lbl)
        v.addLayout(cr)

        self.analyze_btn = QPushButton("Analyser  ▶")
        self.analyze_btn.setObjectName("accent")
        self.analyze_btn.setFixedHeight(42)
        self.analyze_btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.analyze_btn.clicked.connect(self._on_analyze)

        self._cancel_analyze_btn = QPushButton("✕  Annuler")
        self._cancel_analyze_btn.setObjectName("danger")
        self._cancel_analyze_btn.setFixedHeight(42)
        self._cancel_analyze_btn.setFont(QFont("Segoe UI", 13))
        self._cancel_analyze_btn.clicked.connect(self._on_cancel)
        self._cancel_analyze_btn.hide()

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addWidget(self.analyze_btn)
        btn_row.addWidget(self._cancel_analyze_btn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)
        return f

    def _build_step2(self) -> QFrame:
        self._step2 = QFrame()
        self._step2.setStyleSheet(
            f"QFrame {{ background: {BG_SURFACE_1}; border-radius: 12px; }}")
        self._step2.hide()
        g = QGridLayout(self._step2)
        g.setContentsMargins(12, 12, 12, 12)
        g.setSpacing(4)
        g.addWidget(_section_header("ÉTAPE 2 — ANALYSE DU STYLE"), 0, 0, 1, 3)

        edit_hint = QLabel("Modifiables si l'analyse est incorrecte.")
        edit_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-style: italic;")
        g.addWidget(edit_hint, 1, 0, 1, 3)

        fields = [
            ("Vocal presence", "vocal_presence"),
            ("Vocal delivery", "vocal_delivery"),
            ("Song structure", "song_structure"),
            ("Rhyme pattern",  "rhyme_pattern"),
            ("Lyrical tone",   "lyrical_tone"),
            ("Sonic identity", "sonic_identity"),
        ]
        self._analysis_labels: dict[str, QLineEdit] = {}
        for i, (disp, key) in enumerate(fields):
            kl = QLabel(f"{disp} :")
            kl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            kl.setFixedWidth(120)
            g.addWidget(kl, i + 2, 0)
            vl = QLineEdit("—")
            vl.setStyleSheet(
                f"QLineEdit {{ color: {TEXT_PRIMARY}; font-size: 12px;"
                f" background: {BG_SURFACE_2}; border: 1px solid {BG_SURFACE_3};"
                f" border-radius: 4px; padding: 2px 6px; }}")
            if key == "vocal_presence":
                vl.setPlaceholderText("NONE | MINIMAL | MODERATE | FULL")
            g.addWidget(vl, i + 2, 1, 1, 2)
            self._analysis_labels[key] = vl
        g.setColumnStretch(1, 1)

        row = len(fields) + 2
        ll = QLabel("Langue paroles :")
        ll.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        g.addWidget(ll, row, 0)
        self._lang_entry = QLineEdit()
        self._lang_entry.setFixedSize(200, 34)
        g.addWidget(self._lang_entry, row, 1)
        return self._step2

    def _build_step3(self) -> QFrame:
        self._step3 = QFrame()
        self._step3.setStyleSheet(
            f"QFrame {{ background: {BG_SURFACE_1}; border-radius: 12px; }}")
        self._step3.hide()
        v = QVBoxLayout(self._step3)
        v.setContentsMargins(12, 12, 12, 16)
        v.setSpacing(8)
        v.addWidget(_section_header("ÉTAPE 3 — PERSONNALISATION"))

        self._q_widget = QWidget()
        self._q_widget.setStyleSheet("background: transparent;")
        self._q_layout = QVBoxLayout(self._q_widget)
        self._q_layout.setContentsMargins(0, 0, 0, 0)
        self._q_layout.setSpacing(4)
        v.addWidget(self._q_widget)

        self.generate_btn = QPushButton("Générer  ▶")
        self.generate_btn.setObjectName("accent")
        self.generate_btn.setFixedHeight(42)
        self.generate_btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.generate_btn.clicked.connect(self._on_generate)

        self._cancel_generate_btn = QPushButton("✕  Annuler")
        self._cancel_generate_btn.setObjectName("danger")
        self._cancel_generate_btn.setFixedHeight(42)
        self._cancel_generate_btn.setFont(QFont("Segoe UI", 13))
        self._cancel_generate_btn.clicked.connect(self._on_cancel)
        self._cancel_generate_btn.hide()

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addWidget(self.generate_btn)
        btn_row.addWidget(self._cancel_generate_btn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)
        return self._step3

    def _build_step4(self) -> QFrame:
        self._step4 = QFrame()
        self._step4.setStyleSheet(
            f"QFrame {{ background: {BG_SURFACE_1}; border-radius: 12px; }}")
        self._step4.hide()
        v = QVBoxLayout(self._step4)
        v.setContentsMargins(12, 12, 12, 16)
        v.setSpacing(8)

        # Header row: section header + "Copy all" button
        head_w = QWidget()
        head_w.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(head_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        hl.addWidget(_section_header("ÉTAPE 4 — RÉSULTAT"), 1)
        self._copy_all_btn = QPushButton("📋  Tout copier")
        self._copy_all_btn.setFixedSize(140, 32)
        self._copy_all_btn.clicked.connect(self._on_copy_all)
        hl.addWidget(self._copy_all_btn)
        v.addWidget(head_w)

        self._out_title,  self._out_title_badge  = self._output_block(v, "TITRE",        False, 36)
        self._out_style,  self._out_style_badge  = self._output_block(v, "STYLE PROMPT", True,  80)
        self._out_lyrics, self._out_lyrics_badge = self._output_block(v, "PAROLES",      True,  280)

        self._prompt_toggle = QPushButton("▶  Voir le prompt utilisé")
        self._prompt_toggle.setFixedHeight(28)
        self._prompt_toggle.setFont(QFont("Segoe UI", 11))
        self._prompt_toggle.setStyleSheet(
            f"QPushButton {{ background: {BG_SURFACE_2}; color: {TEXT_SECONDARY};"
            f" border: none; border-radius: 6px; text-align: left; padding: 0 10px; }}"
            f"QPushButton:hover {{ background: {BG_SURFACE_3}; color: {TEXT_PRIMARY}; }}")
        self._prompt_toggle.clicked.connect(self._toggle_prompt)
        v.addWidget(self._prompt_toggle)

        self._prompt_box = QTextEdit()
        self._prompt_box.setFixedHeight(150)
        self._prompt_box.setReadOnly(True)
        self._prompt_box.setFont(QFont("Courier New", 11))
        self._prompt_box.hide()
        v.addWidget(self._prompt_box)

        fb_lbl = QLabel("Feedback pour la régénération (optionnel) :")
        fb_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        v.addWidget(fb_lbl)

        self._regen_feedback_entry = QLineEdit()
        self._regen_feedback_entry.setFixedHeight(34)
        self._regen_feedback_entry.setPlaceholderText(
            "Ex : chorus trop générique, manque de basse, paroles trop abstraites, style trop court...")
        self._regen_feedback_entry.setFont(QFont("Segoe UI", 11))
        self._regen_feedback_entry.setStyleSheet(
            f"QLineEdit {{ background: {BG_SURFACE_2}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE_3}; border-radius: 6px; padding: 0 8px; }}")
        v.addWidget(self._regen_feedback_entry)

        br = QHBoxLayout()
        self.regen_btn = QPushButton("Régénérer")
        self.regen_btn.setObjectName("success")
        self.regen_btn.setFixedSize(140, 38)
        self.regen_btn.clicked.connect(self._on_regenerate)
        br.addWidget(self.regen_btn)
        br.addStretch(1)
        v.addLayout(br)

        self._saved_lbl = QLabel("")
        self._saved_lbl.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
        v.addWidget(self._saved_lbl)

        # Session total (tokens + estimated cost), updated on each generation
        self._session_total_lbl = QLabel("")
        self._session_total_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; padding-top: 2px;"
        )
        v.addWidget(self._session_total_lbl)
        return self._step4

    def _output_block(self, parent_layout, label: str,
                      multiline: bool, height: int):
        c = QWidget()
        c.setStyleSheet("background: transparent;")
        cv = QVBoxLayout(c)
        cv.setContentsMargins(0, 4, 0, 0)
        cv.setSpacing(4)

        hdr = QWidget()
        hdr.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        lbl_w = QLabel(label)
        lbl_w.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_w.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hl.addWidget(lbl_w)
        diff_badge = QLabel("")
        diff_badge.setStyleSheet(
            f"color: {WARNING_COL}; font-size: 10px; padding: 1px 6px;"
            f"background: rgba(255, 170, 68, 0.12); border-radius: 8px;"
        )
        diff_badge.setVisible(False)
        hl.addWidget(diff_badge)
        hl.addStretch(1)
        copy_btn = QPushButton("📋 Copier")
        copy_btn.setFixedSize(100, 32)
        copy_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_SURFACE_2}; color: {TEXT_SECONDARY};"
            f" border: none; border-radius: 6px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {ACCENT_DIM}; color: {TEXT_PRIMARY}; }}")
        copy_btn.setToolTip(f"Copier le contenu de « {label} »")
        hl.addWidget(copy_btn)
        cv.addWidget(hdr)

        if multiline:
            w = QTextEdit()
            w.setMinimumHeight(height)
            w.setReadOnly(True)
            copy_btn.clicked.connect(
                lambda _, ww=w, b=copy_btn: _copy_flash(ww.toPlainText().strip(), b))
        else:
            w = QLineEdit()
            w.setFixedHeight(height)
            w.setReadOnly(True)
            copy_btn.clicked.connect(
                lambda _, ww=w, b=copy_btn: _copy_flash(ww.text().strip(), b))
        cv.addWidget(w)
        parent_layout.addWidget(c)
        return w, diff_badge

    def _toggle_prompt(self):
        v = not self._prompt_box.isVisible()
        self._prompt_box.setVisible(v)
        self._prompt_toggle.setText(
            "▼  Masquer le prompt utilisé" if v else "▶  Voir le prompt utilisé")

    # ── HISTORY PANEL ────────────────────────────────────────────────────────

    def _build_history_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG_BASE};")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)

        toolbar = QWidget()
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(16, 12, 16, 4)
        title_w = QLabel("Sessions sauvegardées")
        title_w.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        tl.addWidget(title_w)
        self._hist_count_lbl = QLabel("")
        self._hist_count_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;")
        tl.addWidget(self._hist_count_lbl)
        tl.addStretch(1)
        rb = QPushButton("↺  Rafraîchir")
        rb.setFixedSize(110, 32)
        rb.clicked.connect(self._refresh_history)
        tl.addWidget(rb)
        pv.addWidget(toolbar)

        sb = QWidget()
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(16, 0, 16, 6)
        sl.setSpacing(6)
        self._hist_search = QLineEdit()
        self._hist_search.setPlaceholderText(
            "🔍  Rechercher dans les sessions…")
        self._hist_search.setFixedHeight(34)
        # Debounced live search: textChanged restarts a 250ms one-shot
        self._hist_search_timer = QTimer(self)
        self._hist_search_timer.setSingleShot(True)
        self._hist_search_timer.setInterval(250)
        self._hist_search_timer.timeout.connect(self._hist_apply_search)
        self._hist_search.textChanged.connect(
            lambda _t: self._hist_search_timer.start())
        self._hist_search.returnPressed.connect(self._hist_apply_search)
        sl.addWidget(self._hist_search, 1)
        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(34, 34)
        clear_btn.clicked.connect(self._hist_clear_search)
        sl.addWidget(clear_btn)
        pv.addWidget(sb)

        self._hist_scroll = QScrollArea()
        self._hist_scroll.setWidgetResizable(True)
        self._hist_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._hist_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        self._hist_content = QWidget()
        self._hist_content.setStyleSheet(f"background: {BG_BASE};")
        self._hist_vbox = QVBoxLayout(self._hist_content)
        self._hist_vbox.setContentsMargins(8, 4, 8, 4)
        self._hist_vbox.setSpacing(4)
        self._hist_vbox.addStretch(1)
        self._hist_scroll.setWidget(self._hist_content)
        pv.addWidget(self._hist_scroll, 1)

        pag = QFrame()
        pag.setFixedHeight(40)
        pag.setStyleSheet(f"QFrame {{ background: {BG_SURFACE_1}; }}")
        pl = QHBoxLayout(pag)
        pl.setContentsMargins(10, 0, 10, 0)
        self._hist_prev_btn = QPushButton("◀  Précédent")
        self._hist_prev_btn.setFixedSize(120, 30)
        self._hist_prev_btn.clicked.connect(self._hist_prev_page)
        pl.addWidget(self._hist_prev_btn)
        pl.addStretch(1)
        self._hist_page_lbl = QLabel("")
        self._hist_page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hist_page_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;")
        pl.addWidget(self._hist_page_lbl)
        pl.addStretch(1)
        self._hist_next_btn = QPushButton("Suivant  ▶")
        self._hist_next_btn.setFixedSize(120, 30)
        self._hist_next_btn.clicked.connect(self._hist_next_page)
        pl.addWidget(self._hist_next_btn)
        pv.addWidget(pag)
        return panel

    def _refresh_history(self):
        """Re-query the index (no file I/O until expanded)."""
        self._hist_page = 0
        self._render_history_page()

    def _hist_apply_search(self):
        self._hist_page = 0
        self._render_history_page()

    def _hist_clear_search(self):
        self._hist_search.clear()
        self._hist_page = 0
        self._render_history_page()

    def _hist_prev_page(self):
        if self._hist_page > 0:
            self._hist_page -= 1
            self._render_history_page()

    def _hist_next_page(self):
        total = history_index.count(self._hist_search.text())
        pages = max(1, -(-total // HISTORY_PAGE_SIZE))
        if self._hist_page < pages - 1:
            self._hist_page += 1
            self._render_history_page()

    def _render_history_page(self):
        _clear_layout(self._hist_vbox)

        q = self._hist_search.text().strip()
        try:
            total = history_index.count(q)
            offset = self._hist_page * HISTORY_PAGE_SIZE
            rows = history_index.list_sessions(q, offset, HISTORY_PAGE_SIZE)
        except Exception as e:
            total = 0
            rows = []
            self._update_status(f"Erreur d'index historique : {e}")

        pages = max(1, -(-total // HISTORY_PAGE_SIZE))
        self._hist_page_lbl.setText(
            f"Page {self._hist_page + 1} / {pages}  —  {total} session(s)")
        self._hist_prev_btn.setEnabled(self._hist_page > 0)
        self._hist_next_btn.setEnabled(self._hist_page < pages - 1)

        if total == 0:
            msg = ("Aucun résultat pour cette recherche."
                   if q else "Aucune session sauvegardée.\n"
                             "Générez une composition pour commencer.")
            lbl = QLabel(msg)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
            self._hist_vbox.addWidget(lbl)
            self._hist_count_lbl.setText("")
        else:
            self._hist_count_lbl.setText(
                f"{len(rows)} session(s) sur cette page")
            n_skipped = 0
            for row in rows:
                # Lazy parse: only this page's files are parsed
                parsed = core._parse_session_file(row.file_path)
                if not parsed:
                    n_skipped += 1
                    continue
                card = HistoryCard(parsed)
                card.load_requested.connect(self._load_from_history)
                card.delete_requested.connect(self._confirm_delete)
                self._hist_vbox.addWidget(card)
            if n_skipped:
                warn = QLabel(f"⚠ {n_skipped} fichier(s) illisible(s) sur cette page.")
                warn.setStyleSheet(f"color: {WARNING_COL}; font-size: 11px;")
                self._hist_vbox.addWidget(warn)

        self._hist_vbox.addStretch(1)

    def _load_from_history(self, entry: dict, gen: dict):
        session = core.session_from_history(entry)
        session["title"]                   = gen["title"]
        session["style_prompt"]            = gen["style"]
        session["lyrics"]                  = gen["lyrics"]
        session["generation_count"]        = gen["gen_num"]
        session["last_composition_prompt"] = gen.get("prompt", "")

        if self._llm_client is None:
            cfg = settings.load_config()
            if cfg:
                self._init_client_from_config(cfg)

        self._session = session
        self._sidebar.set_active("generator")
        self._switch_panel("generator")

        self._intent_box.setPlainText(session.get("user_intent", ""))
        for key, lbl in self._analysis_labels.items():
            lbl.setText(session.get(key, "") or "—")
        self._lang_entry.setText(session.get("lyrics_language", ""))
        self._rebuild_question_rows(tweak=True)
        self._set_text(self._out_title,  session["title"])
        self._set_text(self._out_style,  session["style_prompt"])
        self._set_text(self._out_lyrics, session["lyrics"])
        self._prompt_box.setPlainText(
            session.get("last_composition_prompt", ""))
        self._saved_lbl.setText(f"Chargé depuis : {entry['filepath']}")
        self._set_state(AppState.OUTPUT_READY)
        self._update_status(
            f"Session chargée — génération #{gen['gen_num']} : {gen['title']}")

    def _confirm_delete(self, entry: dict):
        sd  = entry["session_data"]
        ref = (sd.get("user_intent")
               or " / ".join(filter(None,
                   [sd.get("style",""), sd.get("artist","")]))
               or "Sans référence")
        if len(ref) > 60:
            ref = ref[:57] + "..."
        n = len(entry["generations"])

        dlg = QDialog(self)
        dlg.setWindowTitle("Confirmer la suppression")
        dlg.setFixedSize(420, 170)
        dlg.setStyleSheet(f"QDialog {{ background: {BG_SURFACE_1}; }}")
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        t = QLabel("Supprimer cette session ?")
        t.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        d = QLabel(f"{ref}  —  {n} génération(s)")
        d.setStyleSheet(f"color: {TEXT_SECONDARY};")
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(d)

        br = QHBoxLayout()
        br.addStretch(1)
        cancel = QPushButton("Annuler")
        cancel.setFixedSize(110, 36)
        cancel.clicked.connect(dlg.reject)
        br.addWidget(cancel)
        del_btn = QPushButton("Supprimer")
        del_btn.setObjectName("danger")
        del_btn.setFixedSize(110, 36)
        del_btn.clicked.connect(lambda: self._do_delete(entry, dlg))
        br.addWidget(del_btn)
        br.addStretch(1)
        v.addLayout(br)
        dlg.exec()

    def _do_delete(self, entry: dict, dlg: QDialog):
        dlg.accept()
        try:
            os.remove(entry["filepath"])
        except OSError as e:
            self._show_error(str(e))
            return
        try:
            history_index.delete_by_path(entry["filepath"])
        except Exception:
            pass
        self._refresh_history()

    # ── SETTINGS PANEL ───────────────────────────────────────────────────────

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG_BASE};")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        inner.setStyleSheet(f"background: {BG_BASE};")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(40, 20, 40, 40)
        iv.setSpacing(8)
        scroll.setWidget(inner)
        pv.addWidget(scroll, 1)

        t = QLabel("Paramètres")
        t.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        iv.addWidget(t)
        div = QFrame()
        div.setFixedHeight(2)
        div.setStyleSheet(f"background: {ACCENT_DIM};")
        iv.addWidget(div)

        # Warning banner
        self._sp_warning = QFrame()
        self._sp_warning.setStyleSheet(
            f"QFrame {{ background: #3a2010; border-radius: 8px;"
            f" border: 1px solid #aa5520; }}")
        wl = QHBoxLayout(self._sp_warning)
        wl.setContentsMargins(16, 10, 16, 10)
        wlbl = QLabel(
            "⚠  Aucune configuration trouvée. "
            "Configurez un provider pour commencer.")
        wlbl.setStyleSheet(f"color: {WARNING_COL}; font-size: 12px;")
        wl.addWidget(wlbl)
        self._sp_warning.hide()
        iv.addWidget(self._sp_warning)

        # Provider
        pl = QLabel("PROVIDER")
        pl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        pl.setStyleSheet(f"color: {ACCENT}; padding-top: 12px;")
        iv.addWidget(pl)

        pgrid = QWidget()
        pgrid.setStyleSheet("background: transparent;")
        pg = QGridLayout(pgrid)
        pg.setContentsMargins(0, 4, 0, 0)
        pg.setSpacing(8)
        for c in range(3):
            pg.setColumnStretch(c, 1)
        self._sp_provider_btns: dict[str, QPushButton] = {}
        for idx, pid in enumerate(PROVIDERS):
            btn = QPushButton(PROVIDERS[pid]["name"])
            btn.setFixedHeight(40)
            btn.setStyleSheet(self._sp_card_style(False))
            btn.clicked.connect(lambda _, p=pid: self._sp_select_provider(p))
            pg.addWidget(btn, idx // 3, idx % 3)
            self._sp_provider_btns[pid] = btn
        iv.addWidget(pgrid)

        # API Key
        kl = QLabel("CLÉ API")
        kl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        kl.setStyleSheet(f"color: {ACCENT}; padding-top: 8px;")
        iv.addWidget(kl)

        kr = QHBoxLayout()
        self._sp_key_entry = QLineEdit()
        self._sp_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._sp_key_entry.setFixedHeight(38)
        kr.addWidget(self._sp_key_entry, 1)
        eye = QPushButton("👁")
        eye.setFixedSize(40, 38)
        eye.clicked.connect(self._sp_toggle_key_vis)
        kr.addWidget(eye)
        self._sp_validate_btn = QPushButton("Valider  ✓")
        self._sp_validate_btn.setObjectName("accent")
        self._sp_validate_btn.setFixedSize(110, 38)
        self._sp_validate_btn.clicked.connect(self._sp_validate_key)
        kr.addWidget(self._sp_validate_btn)
        iv.addLayout(kr)

        self._sp_key_link = QLabel("")
        self._sp_key_link.setStyleSheet(
            f"color: {LINK}; font-size: 11px;")
        self._sp_key_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sp_key_link.mousePressEvent = \
            lambda _e: webbrowser.open(
                PROVIDERS[self._sp_selected_provider]["key_url"])
        iv.addWidget(self._sp_key_link)

        self._sp_key_status = QLabel("")
        self._sp_key_status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;")
        iv.addWidget(self._sp_key_status)

        self._sp_spinner_lbl = QLabel("")
        self._sp_spinner_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px;")
        iv.addWidget(self._sp_spinner_lbl)

        # Model
        ml = QLabel("MODÈLE")
        ml.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ml.setStyleSheet(f"color: {ACCENT}; padding-top: 8px;")
        iv.addWidget(ml)

        self._sp_model_combo = QComboBox()
        self._sp_model_combo.addItem("—")
        self._sp_model_combo.setFixedHeight(38)
        iv.addWidget(self._sp_model_combo)

        hint = QLabel(
            "Pour de meilleurs résultats créatifs, "
            "privilégiez les modèles 'large' ou 'pro'.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        iv.addWidget(hint)

        div2 = QFrame()
        div2.setFixedHeight(1)
        div2.setStyleSheet(f"background: {ACCENT_DIM};")
        iv.addWidget(div2)

        self._sp_save_btn = QPushButton("Sauvegarder les paramètres")
        self._sp_save_btn.setObjectName("accent")
        self._sp_save_btn.setFixedHeight(44)
        self._sp_save_btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._sp_save_btn.setEnabled(False)
        self._sp_save_btn.clicked.connect(self._sp_save)
        iv.addWidget(self._sp_save_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self._sp_save_confirm = QLabel("")
        self._sp_save_confirm.setStyleSheet(
            f"color: {SUCCESS}; font-size: 12px;")
        iv.addWidget(self._sp_save_confirm)

        # ── USAGE ──
        div3 = QFrame()
        div3.setFixedHeight(1)
        div3.setStyleSheet(f"background: {ACCENT_DIM};")
        iv.addWidget(div3)

        ul = QLabel("CONSOMMATION DU MOIS")
        ul.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ul.setStyleSheet(f"color: {ACCENT}; padding-top: 16px;")
        iv.addWidget(ul)

        self._usage_hint = QLabel(
            f"Prix mis à jour le {PRICING_UPDATED_AT}. "
            f"Modèles non listés : coût affiché « ~? »."
        )
        self._usage_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._usage_hint.setWordWrap(True)
        iv.addWidget(self._usage_hint)

        self._usage_grid = QGridLayout()
        self._usage_grid.setHorizontalSpacing(20)
        self._usage_grid.setVerticalSpacing(4)
        usage_container = QWidget()
        usage_container.setStyleSheet("background: transparent;")
        usage_container.setLayout(self._usage_grid)
        iv.addWidget(usage_container)

        refresh_usage = QPushButton("↻  Recalculer")
        refresh_usage.setFixedSize(140, 30)
        refresh_usage.clicked.connect(self._refresh_usage_panel)
        iv.addWidget(refresh_usage, 0, Qt.AlignmentFlag.AlignLeft)

        iv.addStretch(1)

        self._sp_load_existing_config()
        # Initial usage refresh — non-blocking, safe to do at build time
        QTimer.singleShot(500, self._refresh_usage_panel)
        return panel

    def _refresh_usage_panel(self):
        """Populate the usage grid with the current month's aggregates."""
        _clear_layout(self._usage_grid)
        try:
            ym = datetime.datetime.now().strftime("%Y-%m")
            rows = history_index.usage_aggregates(year_month=ym)
        except Exception:
            rows = []
        if not rows:
            empty = QLabel("Aucune utilisation enregistrée ce mois-ci.")
            empty.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            self._usage_grid.addWidget(empty, 0, 0, 1, 5)
            return
        headers = ["Provider", "Modèle", "Sessions", "Tokens", "Coût estimé"]
        for col, txt in enumerate(headers):
            h = QLabel(txt)
            h.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-weight: bold; font-size: 11px;"
            )
            self._usage_grid.addWidget(h, 0, col)
        total_cost = 0.0
        total_known = False
        for i, row in enumerate(rows, 1):
            provider = (row.get("provider") or "?").strip()
            model    = (row.get("model")    or "?").strip()
            n        = row.get("n") or 0
            inp      = row.get("inp") or 0
            outp     = row.get("outp") or 0
            cost     = row.get("cost")
            if cost is not None:
                total_cost += cost
                total_known = True
            tokens_str = f"{inp:,} in / {outp:,} out"
            cost_str = f"~${cost:.4f}" if cost is not None else "~$?"
            cells = [
                PROVIDERS.get(provider, {}).get("name", provider),
                model,
                str(n),
                tokens_str,
                cost_str,
            ]
            for col, t in enumerate(cells):
                lbl = QLabel(t)
                lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px;")
                self._usage_grid.addWidget(lbl, i, col)
        total_lbl = QLabel(
            f"Total mois : {f'~${total_cost:.4f}' if total_known else '~$?'}"
        )
        total_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 12px;")
        self._usage_grid.addWidget(total_lbl, len(rows) + 1, 0, 1, 5)

    @staticmethod
    def _sp_card_style(selected: bool) -> str:
        if selected:
            return (f"QPushButton {{ background: {BG_SURFACE_3};"
                    f" color: {TEXT_PRIMARY}; border: 2px solid {ACCENT};"
                    f" border-radius: 8px; padding: 10px; }}")
        return (f"QPushButton {{ background: {BG_SURFACE_2};"
                f" color: {TEXT_SECONDARY}; border: 2px solid {BG_SURFACE_2};"
                f" border-radius: 8px; padding: 10px; }}"
                f"QPushButton:hover {{ border-color: {ACCENT_DIM};"
                f" color: {TEXT_PRIMARY}; }}")

    def _sp_select_provider(self, pid: str, load_key: bool = True):
        self._sp_selected_provider = pid
        for p, btn in self._sp_provider_btns.items():
            btn.setStyleSheet(self._sp_card_style(p == pid))
        if load_key:
            self._sp_key_entry.setText(settings.get_api_key(pid) or "")
            self._sp_key_status.setText("")
            self._sp_spinner_lbl.setText("")
            self._sp_models = []
            self._sp_model_combo.clear()
            self._sp_model_combo.addItem("—")
            self._sp_save_btn.setEnabled(False)
            self._sp_key_validated = False
            url = PROVIDERS[pid]["key_url"]
            self._sp_key_link.setText(f"→ Obtenir une clé : {url}")

    def _sp_load_existing_config(self):
        pid   = settings.get_current_provider() or "openai"
        model = settings.get_current_model() or ""
        key   = settings.get_api_key(pid) or ""
        self._sp_select_provider(pid, load_key=False)
        url = PROVIDERS[pid]["key_url"]
        self._sp_key_link.setText(f"→ Obtenir une clé : {url}")
        if key:
            self._sp_key_entry.setText(key)
        if model:
            self._sp_models = [model] + [m for m in PROVIDERS[pid]["default_models"]
                                          if m != model]
            self._sp_model_combo.clear()
            self._sp_model_combo.addItems(self._sp_models)
            self._sp_model_combo.setCurrentText(model)
            self._sp_save_btn.setEnabled(True)
            self._sp_key_validated = True

    def _sp_toggle_key_vis(self):
        m = QLineEdit.EchoMode
        self._sp_key_entry.setEchoMode(
            m.Normal if self._sp_key_entry.echoMode() == m.Password
            else m.Password)

    def _sp_validate_key(self):
        key = self._sp_key_entry.text().strip()
        if not key:
            self._sp_key_status.setStyleSheet(
                f"color: {ERROR_COL}; font-size: 12px;")
            self._sp_key_status.setText("⚠ La clé ne peut pas être vide.")
            return
        self._sp_validate_btn.setEnabled(False)
        self._sp_save_btn.setEnabled(False)
        self._sp_key_status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;")
        self._sp_key_status.setText("Validation en cours...")
        self._sp_key_validated = False
        self._sp_spinner_dots = 0
        self._sp_spinner_timer.start()

        worker = ValidateKeyWorker(self._sp_selected_provider, key)
        worker.finished.connect(self._sp_on_validated)
        worker.stopped.connect(self._sp_spinner_timer.stop)
        self._sp_thread = _launch(worker)

    def _sp_tick_spinner(self):
        dots = "." * (self._sp_spinner_dots % 4)
        self._sp_spinner_lbl.setText(f"Chargement des modèles{dots}")
        self._sp_spinner_dots += 1

    def _sp_on_validated(self, ok: bool, msg: str, models: list):
        self._sp_spinner_lbl.setText("")
        self._sp_validate_btn.setEnabled(True)
        if ok:
            self._sp_key_status.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px;")
            self._sp_key_status.setText(f"✓ {msg}")
            self._sp_key_validated = True
            pid = self._sp_selected_provider
            self._sp_models = models or PROVIDERS[pid]["default_models"]
            self._sp_model_combo.clear()
            self._sp_model_combo.addItems(self._sp_models)
            self._sp_model_combo.setCurrentIndex(0)
            self._sp_save_btn.setEnabled(True)
        else:
            self._sp_key_status.setStyleSheet(
                f"color: {ERROR_COL}; font-size: 12px;")
            self._sp_key_status.setText(f"✗ {msg}")

    def _sp_save(self):
        pid   = self._sp_selected_provider
        key   = self._sp_key_entry.text().strip()
        model = self._sp_model_combo.currentText().strip()
        if not key or not model or model == "—":
            return
        settings.save_config(pid, model, key)
        self._sp_warning.hide()
        self._on_settings_saved(pid, key, model)
        self._sp_save_confirm.setText("✓ Paramètres sauvegardés")
        QTimer.singleShot(3000, lambda: self._sp_save_confirm.setText(""))

    def _sp_show_warning(self, v: bool):
        self._sp_warning.setVisible(v)

    # ── FADE / FOCUS HELPERS ─────────────────────────────────────────────────

    def _fade_widget(self, w: QWidget, show: bool) -> None:
        """Fade a widget in or out using QGraphicsOpacityEffect.

        Skips animation when the visibility state is already correct.
        """
        if show == w.isVisible():
            return
        eff = w.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(eff)
        if not hasattr(self, "_active_anims"):
            self._active_anims: list[QPropertyAnimation] = []
        # Drop finished animations to avoid unbounded list growth
        self._active_anims = [
            a for a in self._active_anims
            if a.state() == QPropertyAnimation.State.Running
        ]
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        if show:
            w.show()
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
        else:
            anim.setEasingCurve(QEasingCurve.Type.InCubic)
            anim.setStartValue(eff.opacity())
            anim.setEndValue(0.0)
            anim.finished.connect(w.hide)
        self._active_anims.append(anim)
        anim.start()

    def _clear_output_fields(self) -> None:
        """Wipe Step 4 outputs and prompt box (used before regeneration)."""
        self._set_text(self._out_title,  "")
        self._set_text(self._out_style,  "")
        self._set_text(self._out_lyrics, "")
        self._prompt_box.clear()
        self._saved_lbl.setText("")
        self._out_title_badge.setVisible(False)
        self._out_style_badge.setVisible(False)
        self._out_lyrics_badge.setVisible(False)

    def _on_copy_all(self) -> None:
        s = self._session
        text = (
            f"# {s.get('title', '')}\n\n"
            f"## STYLE\n{s.get('style_prompt', '')}\n\n"
            f"## LYRICS\n{s.get('lyrics', '')}\n"
        )
        QApplication.clipboard().setText(text)
        _copy_flash(text, self._copy_all_btn)

    # ── COST / USAGE ─────────────────────────────────────────────────────────

    def _on_usage(self, rec: dict) -> None:
        """Slot for the per-call usage signal — refresh the cost badge live."""
        self._refresh_cost_badge()

    def _refresh_cost_badge(self) -> None:
        usage = self._session.get("usage") or []
        in_tok = sum((u.get("input_tokens") or 0) for u in usage)
        out_tok = sum((u.get("output_tokens") or 0) for u in usage)
        costs = [u.get("cost_usd") for u in usage]
        cost = sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None
        self._stepper.set_cost(in_tok, out_tok, cost)

    def _refresh_session_total(self) -> None:
        usage = self._session.get("usage") or []
        if not usage:
            self._session_total_lbl.setText("")
            return
        in_tok = sum((u.get("input_tokens") or 0) for u in usage)
        out_tok = sum((u.get("output_tokens") or 0) for u in usage)
        costs = [u.get("cost_usd") for u in usage]
        cost_str = (
            f"~${sum(c for c in costs if c is not None):.4f}"
            if any(c is not None for c in costs) else "~$?"
        )
        n_calls = len(usage)
        self._session_total_lbl.setText(
            f"Total session : {in_tok:,} in / {out_tok:,} out — "
            f"{n_calls} appel(s) — coût estimé {cost_str}"
        )

    def _update_diff_badges(self, prev: dict | None) -> None:
        """Show modifié/inchangé badges next to each output, post-regeneration."""
        if not prev:
            self._out_title_badge.setVisible(False)
            self._out_style_badge.setVisible(False)
            self._out_lyrics_badge.setVisible(False)
            return
        s = self._session

        def _badge(badge: QLabel, current: str, previous: str) -> None:
            if not previous:
                badge.setVisible(False)
                return
            ratio = difflib.SequenceMatcher(None, previous, current).ratio()
            if ratio > 0.95:
                badge.setText("inchangé")
                badge.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 10px; padding: 1px 6px;"
                    f"background: rgba(85, 85, 112, 0.18); border-radius: 8px;"
                )
            else:
                badge.setText("modifié")
                badge.setStyleSheet(
                    f"color: {WARNING_COL}; font-size: 10px; padding: 1px 6px;"
                    f"background: rgba(255, 170, 68, 0.14); border-radius: 8px;"
                )
            badge.setVisible(True)

        _badge(self._out_title_badge,  s.get("title", ""),        prev.get("title", ""))
        _badge(self._out_style_badge,  s.get("style_prompt", ""), prev.get("style_prompt", ""))
        _badge(self._out_lyrics_badge, s.get("lyrics", ""),       prev.get("lyrics", ""))

    def _on_rate_limit(self, wait_seconds: float) -> None:
        """Show the rate-limit banner with a countdown."""
        self._rate_limit_banner.start_countdown(wait_seconds)

    # ── STATE MACHINE ────────────────────────────────────────────────────────

    def _set_state(self, state: AppState):
        self._state = state
        busy        = state in (AppState.ANALYZING, AppState.GENERATING)
        questions_v = state in (AppState.QUESTIONS_READY,
                                AppState.GENERATING, AppState.OUTPUT_READY)
        out_ready   = state == AppState.OUTPUT_READY

        self.analyze_btn.setEnabled(not busy)
        # Keep legacy step-level cancel buttons hidden — LoadingCard owns the action
        self._cancel_analyze_btn.setVisible(False)
        self._cancel_generate_btn.setVisible(False)
        # Step 2 + 3 visibility with fade
        self._fade_widget(self._step2, questions_v)
        self._lang_entry.setEnabled(not busy)
        self._fade_widget(self._step3, questions_v)
        for e in self._question_entries:
            try:
                e.setEnabled(not busy)
            except AttributeError:
                pass
        self.generate_btn.setEnabled(not busy)
        # Step 4: ONLY visible when output is ready. During GENERATING the LoadingCard takes over.
        self._fade_widget(self._step4, out_ready)
        self.regen_btn.setEnabled(out_ready)
        self._prompt_toggle.setEnabled(out_ready)
        if hasattr(self, "_regen_feedback_entry"):
            self._regen_feedback_entry.setEnabled(out_ready)
        self._stepper.update_state(state)

        # Loading card — the prominent in-flow indicator
        if state == AppState.ANALYZING:
            self._loading_card.show_for_phase("🎼  Analyse du style en cours…")
        elif state == AppState.GENERATING:
            self._loading_card.show_for_phase("🎤  Génération de la composition…")
        else:
            self._fade_widget(self._loading_card, False)

        # Step focus dimming — active step at 1.0, others at 0.55
        self._apply_step_focus(state)

    def _apply_step_focus(self, state: AppState) -> None:
        """Dim non-active step frames to focus attention without losing context."""
        mapping = {
            AppState.IDLE:            self._step1_frame,
            AppState.ANALYZING:       self._step1_frame,
            AppState.QUESTIONS_READY: self._step3,
            AppState.GENERATING:      self._step3,
            AppState.OUTPUT_READY:    self._step4,
        }
        active = mapping.get(state)
        for w in (self._step1_frame, self._step2, self._step3, self._step4):
            if not w.isVisible():
                continue
            eff = w.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(w)
                w.setGraphicsEffect(eff)
            eff.setOpacity(1.0 if w is active else 0.55)

    # ── SPINNER + STATUS ─────────────────────────────────────────────────────

    def _tick_spinner(self):
        chars = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spinner_lbl.setText(chars[self._spinner_tick % len(chars)])
        self._spinner_tick += 1

    def _update_status(self, text: str):
        self._status_lbl.setText(text)

    # ── MISC HELPERS ─────────────────────────────────────────────────────────

    def _update_char_count(self):
        text = self._intent_box.toPlainText()
        n = len(text)
        if n > INTENT_MAX_CHARS:
            cursor = self._intent_box.textCursor()
            self._intent_box.blockSignals(True)
            self._intent_box.setPlainText(text[:INTENT_MAX_CHARS])
            self._intent_box.setTextCursor(cursor)
            self._intent_box.blockSignals(False)
            n = INTENT_MAX_CHARS
        color = (ERROR_COL if n > 1800
                 else (WARNING_COL if n > 1500 else TEXT_MUTED))
        self._char_lbl.setText(f"{n} / {INTENT_MAX_CHARS}")
        self._char_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _set_text(self, widget, text: str):
        if isinstance(widget, QTextEdit):
            widget.setPlainText(text)
        else:
            widget.setText(text)

    _IMPACT_LABELS = {
        "theme":           "thème des paroles",
        "imagery":         "imagerie concrète",
        "energy_arc":      "arc énergétique",
        "vocal_register":  "registre vocal",
        "language_switch": "changement de langue",
        "section_focus":   "section ciblée",
    }

    def _rebuild_question_rows(self, tweak: bool = False):
        _clear_layout(self._q_layout)
        self._question_entries.clear()
        self._question_labels.clear()

        # Prefer typed questions (new format). Fall back to legacy split.
        typed = self._session.get("questions") or []
        if not typed:
            raw = self._session.get("questions_raw", "")
            typed = [
                {"id": f"q{i+1}", "type": "free", "prompt": p.strip(), "options": [],
                 "impact": "theme"}
                for i, p in enumerate(raw.split("|")) if p.strip()
            ]
        if not typed:
            vp = self._session.get("vocal_presence", "FULL")
            default_prompt = ("Mood ou atmosphère du track ?"
                              if vp in ("NONE", "MINIMAL")
                              else "Thème ou sujet de la chanson ?")
            typed = [{"id": "q1", "type": "free", "prompt": default_prompt,
                      "options": [], "impact": "theme"}]

        prev = {q: a for q, a in self._session.get("answers", [])}

        for q in typed:
            prompt_text = q.get("prompt", "")
            options = q.get("options") or []
            qtype = q.get("type", "free")
            impact = q.get("impact", "")

            ql = QLabel(prompt_text)
            ql.setFont(QFont("Segoe UI", 13))
            ql.setWordWrap(True)
            ql.setStyleSheet(f"color: {TEXT_PRIMARY};")
            self._q_layout.addWidget(ql)

            if impact:
                impact_label = self._IMPACT_LABELS.get(impact, impact)
                cap = QLabel(f"impacte : {impact_label}")
                cap.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 10px; font-style: italic;"
                )
                self._q_layout.addWidget(cap)

            if qtype in ("single", "multi") and options:
                group = ChipGroup(options, multi=(qtype == "multi"))
                if tweak and prompt_text in prev and prev[prompt_text]:
                    group.set_value(prev[prompt_text])
                self._q_layout.addWidget(group)
                self._question_entries.append(group)
            else:
                entry = QLineEdit()
                placeholder = "Votre réponse (optionnel)…"
                # Use first option as a placeholder example if provided
                if options:
                    placeholder = f"Ex : {options[0]}"
                entry.setPlaceholderText(placeholder)
                entry.setFixedHeight(34)
                if tweak and prompt_text in prev and prev[prompt_text]:
                    entry.setText(prev[prompt_text])
                self._q_layout.addWidget(entry)
                self._question_entries.append(entry)
            self._question_labels.append(prompt_text)

    def _read_answer(self, entry) -> str:
        """Read the answer string from a question widget (ChipGroup or QLineEdit)."""
        if isinstance(entry, ChipGroup):
            return entry.value()
        if hasattr(entry, "text"):
            return entry.text().strip()
        return ""

    def _show_error(self, message: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("Erreur")
        dlg.setFixedSize(480, 200)
        dlg.setStyleSheet(f"QDialog {{ background: {BG_SURFACE_1}; }}")
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)
        t = QLabel("Une erreur est survenue")
        t.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        m = QLabel(message)
        m.setStyleSheet(f"color: {ERROR_COL}; font-size: 12px;")
        m.setWordWrap(True)
        m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(m, 1)
        close = QPushButton("Fermer")
        close.setObjectName("accent")
        close.setFixedSize(100, 36)
        close.clicked.connect(dlg.accept)
        v.addWidget(close, 0, Qt.AlignmentFlag.AlignHCenter)
        dlg.exec()

    def resizeEvent(self, event):
        """Adapt UI density on narrow windows."""
        super().resizeEvent(event)
        w = self.width()
        if hasattr(self, "_stepper"):
            self._stepper.set_compact(w < 760)
        if hasattr(self, "_sidebar"):
            # Auto-collapse sidebar on narrow windows; preserve user toggle when wide
            if w < 920 and self._sidebar._expanded:
                self._sidebar.toggle()
            elif w >= 1100 and not self._sidebar._expanded:
                self._sidebar.toggle()

    def eventFilter(self, obj, event):
        """Ctrl+Enter in intent box → analyze."""
        if obj is self._intent_box and event.type() == QEvent.Type.KeyPress:
            ke: QKeyEvent = event
            if (ke.key() == Qt.Key.Key_Return
                    and ke.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._on_analyze()
                return True
        return super().eventFilter(obj, event)

    # ── CONFIG ───────────────────────────────────────────────────────────────

    def _check_config_on_start(self):
        cfg = settings.load_config()
        if not cfg:
            self._sidebar.set_active("settings")
            self._switch_panel("settings")
            self._sp_show_warning(True)
        else:
            self._init_client_from_config(cfg)

    def _init_client_from_config(self, cfg: dict):
        pid   = cfg["provider"]
        model = cfg["model"]
        key   = settings.get_api_key(pid) or ""
        if key:
            try:
                self._llm_client = LLMClient(pid, key, model)
                self._session["provider"] = pid
                self._session["model"]    = model
                name = PROVIDERS[pid]["name"]
                self._sidebar.set_provider_text(f"{name}  ·  {model}")
                self._update_status(f"Prêt — {name} / {model}")
            except Exception as e:
                self._update_status(f"Erreur d'initialisation: {e}")

    def _on_settings_saved(self, provider: str, api_key: str, model: str):
        try:
            self._llm_client = LLMClient(provider, api_key, model)
            self._session["provider"] = provider
            self._session["model"]    = model
            name = PROVIDERS[provider]["name"]
            self._sidebar.set_provider_text(f"{name}  ·  {model}")
            self._update_status(f"Prêt — {name} / {model}")
        except Exception as e:
            self._show_error(str(e))

    # ── PHASE 1 ──────────────────────────────────────────────────────────────

    def _on_analyze(self):
        if self._llm_client is None:
            self._sidebar.set_active("settings")
            self._switch_panel("settings")
            self._sp_show_warning(True)
            return
        user_intent = self._intent_box.toPlainText().strip()
        if not user_intent:
            self._update_status("⚠ Décrivez ce que vous souhaitez créer.")
            return
        self._session                = core.init_session()
        self._session["user_intent"] = user_intent
        self._session["provider"]    = self._llm_client.provider_id
        self._session["model"]       = self._llm_client.model
        self._rate_limit_banner.dismiss()
        self._refresh_cost_badge()
        self._session_total_lbl.setText("")
        self._clear_output_fields()
        self._set_state(AppState.ANALYZING)
        self._update_status("Analyse en cours…")
        worker = AnalyzeWorker(self._llm_client, self._session)
        worker.finished.connect(self._on_analysis_done)
        worker.error.connect(self._on_error_analyze)
        worker.status.connect(self._update_status)
        worker.usage.connect(self._on_usage)
        worker.rate_limit.connect(self._on_rate_limit)
        worker.cancelled.connect(self._on_cancelled)
        self._current_worker    = worker
        self._cancel_returns_to = AppState.IDLE
        self._worker_thread = _launch(worker)

    def _on_analysis_done(self):
        s = self._session
        for key in ("vocal_presence", "vocal_delivery", "song_structure",
                    "rhyme_pattern", "lyrical_tone", "sonic_identity"):
            if key in self._analysis_labels:
                self._analysis_labels[key].setText(s.get(key, "") or "—")
        lang = s["detected_language"]
        if s["vocal_presence"] == "NONE" or lang.lower() == "instrumental":
            lang = "instrumental"
        self._lang_entry.setText(lang)
        self._rate_limit_banner.dismiss()
        self._set_state(AppState.QUESTIONS_READY)
        self._rebuild_question_rows(tweak=False)
        self._refresh_cost_badge()
        self._update_status(
            "Analyse terminée — répondez aux questions puis cliquez sur Générer.")

    def _on_error_analyze(self, msg: str):
        self._set_state(AppState.IDLE)
        self._update_status(f"Erreur Phase 1: {msg}")
        self._show_error(msg)

    # ── PHASE 3 ──────────────────────────────────────────────────────────────

    def _on_generate(self):
        if self._llm_client is None:
            return

        # Read potentially edited analysis fields back into session
        editable_fields = [
            "vocal_presence", "vocal_delivery", "song_structure",
            "rhyme_pattern", "lyrical_tone", "sonic_identity",
        ]
        for field in editable_fields:
            if field in self._analysis_labels:
                val = self._analysis_labels[field].text().strip()
                if val and val != "—":
                    self._session[field] = val
        # Normalise and validate VOCAL_PRESENCE
        vp = self._session.get("vocal_presence", "FULL").upper().split()[0]
        if vp not in core.VALID_VOCAL_PRESENCE:
            self._update_status(
                f"VOCAL_PRESENCE invalide : '{vp}'. Utilisez NONE / MINIMAL / MODERATE / FULL.")
            return
        self._session["vocal_presence"] = vp

        self._session["lyrics_language"] = (
            self._lang_entry.text().strip()
            or self._session["detected_language"])

        # Read answers using polymorphic _read_answer (handles chips + text)
        labels = self._question_labels
        entries = self._question_entries
        self._session["answers"] = [
            (labels[i], self._read_answer(entries[i]))
            for i in range(min(len(labels), len(entries)))
        ]
        # Snapshot previous output for diff (this is the first generation case)
        self._prev_output = None
        self._clear_output_fields()
        self._rate_limit_banner.dismiss()
        self._set_state(AppState.GENERATING)
        self._update_status("Génération de la composition…")
        worker = GenerateWorker(self._llm_client, self._session)
        worker.finished.connect(self._on_generation_done)
        worker.error.connect(self._on_error_generate)
        worker.status.connect(self._update_status)
        worker.usage.connect(self._on_usage)
        worker.rate_limit.connect(self._on_rate_limit)
        worker.cancelled.connect(self._on_cancelled)
        self._current_worker    = worker
        self._cancel_returns_to = AppState.QUESTIONS_READY
        self._worker_thread = _launch(worker)

    def _on_generation_done(self, filepath: str):
        s = self._session
        prev = getattr(self, "_prev_output", None)
        self._set_text(self._out_title,  s["title"])
        self._set_text(self._out_style,  s["style_prompt"])
        self._set_text(self._out_lyrics, s["lyrics"])
        self._prompt_box.setPlainText(
            s.get("last_composition_prompt", ""))
        self._saved_lbl.setText(f"✓ Sauvegardé : {filepath}")
        self._regen_feedback_entry.clear()
        self._session["regen_feedback"] = ""
        self._update_diff_badges(prev)
        self._refresh_cost_badge()
        self._refresh_session_total()
        # Update the history index in the background
        try:
            history_index.upsert_from_parsed(core._parse_session_file(filepath))
        except Exception:
            pass
        self._rate_limit_banner.dismiss()
        self._set_state(AppState.OUTPUT_READY)
        self._update_status(
            f"Génération #{s['generation_count']} terminée — {s['title']}")

    def _on_error_generate(self, msg: str):
        self._set_state(AppState.QUESTIONS_READY)
        self._update_status(f"Erreur Phase 3: {msg}")
        self._show_error(msg)

    def _on_regenerate(self):
        # Snapshot current output BEFORE wiping — used for the diff badge
        self._prev_output = {
            "title":        self._session.get("title", ""),
            "style_prompt": self._session.get("style_prompt", ""),
            "lyrics":       self._session.get("lyrics", ""),
        }
        self._session["regen_feedback"] = self._regen_feedback_entry.text().strip()
        # Clear visible output BEFORE switching state — the LoadingCard takes over
        self._clear_output_fields()
        self._rate_limit_banner.dismiss()
        self._set_state(AppState.GENERATING)
        self._update_status("Régénération en cours…")
        worker = GenerateWorker(self._llm_client, self._session)
        worker.finished.connect(self._on_generation_done)
        worker.error.connect(self._on_error_generate)
        worker.status.connect(self._update_status)
        worker.usage.connect(self._on_usage)
        worker.rate_limit.connect(self._on_rate_limit)
        worker.cancelled.connect(self._on_cancelled)
        self._current_worker    = worker
        self._cancel_returns_to = AppState.OUTPUT_READY
        self._worker_thread = _launch(worker)

    def _on_cancel(self):
        if self._current_worker is not None:
            self._current_worker.cancel()
        self._update_status("Annulation en cours...")

    def _on_cancelled(self):
        self._set_state(self._cancel_returns_to)
        self._current_worker = None
        self._update_status("Requête annulée.")

    def _on_regen_shortcut(self):
        if self._state == AppState.OUTPUT_READY:
            self._on_regenerate()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main():
    # Enable high-DPI — Qt6 handles multi-monitor DPI changes natively,
    # no custom workaround needed.
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.show()

    # Dark title bar on Windows 10/11
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = int(window.winId())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        except Exception:
            pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
