"""
啟動選擇視窗
讓使用者選擇「即時分析」或「上傳影片分析」
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from .styles import (
    LAUNCHER_BG_STYLE,
    LAUNCHER_CENTRAL_STYLE,
    HEADER_CARD_STYLE,
    MODE_CARD_STYLE,
    LAUNCH_BTN_EMERALD,
    LAUNCH_BTN_BLUE,
)
from .language import language_manager, t
from .dialogs import LanguageSelectionDialog


class LauncherWindow(QMainWindow):
    """
    系統首頁 — 選擇分析模式

    Signals:
        realtime_requested: 使用者點選「即時分析」
        upload_requested:   使用者點選「上傳影片分析」
        history_requested:  使用者點選「分析紀錄」
    """

    realtime_requested = pyqtSignal()
    upload_requested   = pyqtSignal()
    history_requested  = pyqtSignal()

    def __init__(self):
        super().__init__()
        language_manager.add_observer(self.on_language_changed)
        self.setMinimumSize(860, 560)
        self.resize(960, 620)
        self.setStyleSheet(LAUNCHER_BG_STYLE)
        self._init_ui()
        self._retranslate_ui()

    # ------------------------------------------------------------------
    def _init_ui(self):
        central = QWidget()
        central.setObjectName('launcher_bg')
        central.setStyleSheet(LAUNCHER_CENTRAL_STYLE)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setSpacing(28)
        outer.setContentsMargins(48, 40, 48, 40)

        outer.addWidget(self._build_header())

        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)

        realtime_card, self._realtime_title_lbl, self._realtime_desc_lbl, self._realtime_btn = \
            self._build_mode_card(
                icon        = '📹',
                badge_text  = 'LIVE',
                badge_color = '#10b981',
                btn_style   = LAUNCH_BTN_EMERALD,
                callback    = self.realtime_requested.emit,
            )
        cards_row.addWidget(realtime_card)

        upload_card, self._upload_title_lbl, self._upload_desc_lbl, self._upload_btn = \
            self._build_mode_card(
                icon        = '📂',
                badge_text  = 'OFFLINE',
                badge_color = '#3b82f6',
                btn_style   = LAUNCH_BTN_BLUE,
                callback    = self.upload_requested.emit,
            )
        cards_row.addWidget(upload_card)

        outer.addLayout(cards_row)
        outer.addWidget(self._build_footer())

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName('header_card')
        card.setStyleSheet(HEADER_CARD_STYLE)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(card)
        row.setContentsMargins(24, 18, 24, 18)
        row.setSpacing(16)

        icon_lbl = QLabel('📊')
        icon_lbl.setFixedSize(52, 52)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #10b981, stop:1 #059669);
                border-radius: 12px;
                font-size: 24px;
                color: white;
            }
        """)
        row.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._header_title = QLabel()
        self._header_title.setFont(QFont('Microsoft JhengHei', 18, QFont.Weight.Bold))
        self._header_title.setStyleSheet('color: #0f172a;')
        text_col.addWidget(self._header_title)

        self._header_sub = QLabel()
        self._header_sub.setStyleSheet('color: #64748b; font-size: 13px;')
        text_col.addWidget(self._header_sub)

        row.addLayout(text_col)
        row.addStretch()

        # Language toggle button
        self._lang_btn = QPushButton('🌐')
        self._lang_btn.setFixedSize(40, 40)
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_btn.setToolTip('Switch language / 切換語言')
        self._lang_btn.setStyleSheet("""
            QPushButton {
                background: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                font-size: 18px;
            }
            QPushButton:hover { background: #e2e8f0; }
        """)
        self._lang_btn.clicked.connect(self._show_language_dialog)
        row.addWidget(self._lang_btn)

        return card

    # ── Mode card ─────────────────────────────────────────────────────────────
    def _build_mode_card(self, icon, badge_text, badge_color,
                         btn_style, callback):
        """Returns (card, title_lbl, desc_lbl, btn)."""
        card = QFrame()
        card.setObjectName('mode_card')
        card.setStyleSheet(MODE_CARD_STYLE)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        col = QVBoxLayout(card)
        col.setContentsMargins(28, 28, 28, 28)
        col.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedSize(56, 56)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {badge_color}33, stop:1 {badge_color}22);
                border-radius: 14px;
                font-size: 28px;
                color: {badge_color};
            }}
        """)
        top_row.addWidget(icon_lbl)

        badge = QLabel(badge_text)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(24)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {badge_color};
                color: white;
                font-size: 11px;
                font-weight: bold;
                border-radius: 10px;
                padding: 0 10px;
            }}
        """)
        top_row.addStretch()
        top_row.addWidget(badge)
        col.addLayout(top_row)

        title_lbl = QLabel()
        title_lbl.setFont(QFont('Microsoft JhengHei', 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet('color: #0f172a;')
        col.addWidget(title_lbl)

        desc_lbl = QLabel()
        desc_lbl.setStyleSheet('color: #64748b; font-size: 13px; line-height: 1.5;')
        desc_lbl.setWordWrap(True)
        col.addWidget(desc_lbl)

        col.addStretch()

        btn = QPushButton()
        btn.setStyleSheet(btn_style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        col.addWidget(btn)

        return card, title_lbl, desc_lbl, btn

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        self._history_btn = QPushButton()
        self._history_btn.setFlat(True)
        self._history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_btn.setStyleSheet("""
            QPushButton {
                color: rgba(255,255,255,0.7);
                font-size: 13px;
                border: none;
                background: transparent;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: white;
                text-decoration: underline;
            }
        """)
        self._history_btn.clicked.connect(self.history_requested.emit)
        layout.addWidget(self._history_btn)

        return row

    # ── Language ──────────────────────────────────────────────────────────────
    def _show_language_dialog(self):
        dlg = LanguageSelectionDialog(self)
        if dlg.exec():
            language_manager.set_language(dlg.get_selected_language())

    def on_language_changed(self, _lang_code):
        self._retranslate_ui()

    def _retranslate_ui(self):
        self.setWindowTitle(t('launcher_window_title'))
        self._header_title.setText(t('launcher_title'))
        self._header_sub.setText(t('launcher_subtitle'))

        self._realtime_title_lbl.setText(t('launcher_realtime_title'))
        self._realtime_desc_lbl.setText(t('launcher_realtime_desc'))
        self._realtime_btn.setText(t('launcher_realtime_btn'))

        self._upload_title_lbl.setText(t('launcher_upload_title'))
        self._upload_desc_lbl.setText(t('launcher_upload_desc'))
        self._upload_btn.setText(t('launcher_upload_btn'))

        self._history_btn.setText(t('launcher_history_btn'))
