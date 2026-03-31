"""
分析結果視窗（獨立頁面）
對應 Vue [id].vue：含骨架疊加的採樣畫面播放、上下幀切換、
折線圖點擊跳幀、長條圖、統計卡片。
"""

import os
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame, QSizePolicy, QCheckBox,
    QFileDialog, QMessageBox, QScrollArea, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QFont

from ..core.video_file_processor import export_csv
from .styles import (
    UPLOAD_BG_STYLE, CONTENT_CARD_STYLE, HEADER_CARD_STYLE,
    BACK_BTN_STYLE, EMERALD_BTN_STYLE,
)
from .language import language_manager, t


# ──────────────────────────────────────────────────────────────────────────────
# MediaPipe standard pose connections (33 keypoints)
# ──────────────────────────────────────────────────────────────────────────────
_POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12),
    (11, 13), (13, 15), (15, 17), (15, 19), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (18, 20),
    (15, 21), (16, 22),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (27, 31), (29, 31),
    (24, 26), (26, 28), (28, 30), (28, 32), (30, 32),
]
_RULA_KEYPOINTS = {0, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 23, 24}

_SCORE_COLORS = {
    1: ('#d1fae5', '#065f46'), 2: ('#d1fae5', '#065f46'),
    3: ('#fef3c7', '#92400e'), 4: ('#fef3c7', '#92400e'),
    5: ('#fee2e2', '#991b1b'), 6: ('#fee2e2', '#991b1b'),
    7: ('#fca5a5', '#7c2d12'),
}


def _draw_skeleton(frame_rgb: np.ndarray,
                   landmarks_2d: list,
                   threshold: float = 0.25) -> np.ndarray:
    """
    landmarks_2d: list of [x_norm, y_norm, conf] × 33 (normalized 0–1)
    Returns a new RGB frame with skeleton drawn.
    """
    out = frame_rgb.copy()
    h, w = out.shape[:2]

    for (i, j) in _POSE_CONNECTIONS:
        if i >= len(landmarks_2d) or j >= len(landmarks_2d):
            continue
        li, lj = landmarks_2d[i], landmarks_2d[j]
        if li[2] < threshold or lj[2] < threshold:
            continue
        xi, yi = int(li[0] * w), int(li[1] * h)
        xj, yj = int(lj[0] * w), int(lj[1] * h)
        cv2.line(out, (xi, yi), (xj, yj), (0, 230, 118), 2)

    for k, lm in enumerate(landmarks_2d):
        if lm[2] < threshold:
            continue
        x, y = int(lm[0] * w), int(lm[1] * h)
        radius = 5 if k in _RULA_KEYPOINTS else 3
        color  = (255, 82, 82) if k in _RULA_KEYPOINTS else (255, 180, 0)
        cv2.circle(out, (x, y), radius, color, -1)

    return out


def _frame_rgb_from_video(cap: cv2.VideoCapture,
                           frame_idx: int) -> np.ndarray | None:
    """Seek to `frame_idx` and return a decoded RGB frame, or None."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, bgr = cap.read()
    if not ret or bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


# ──────────────────────────────────────────────────────────────────────────────
class ResultWindow(QMainWindow):
    """
    獨立的分析結果視窗。

    Signals:
        back_requested: 使用者按「關閉」或視窗關閉
    """

    back_requested = pyqtSignal()

    def __init__(self, results: dict):
        super().__init__()
        language_manager.add_observer(self.on_language_changed)

        self._results   = results
        self._records   = results.get('records', [])
        self._video_path = results.get('video_path', '')
        self._cap: cv2.VideoCapture | None = None

        # playback state
        self._current_idx = 0
        self._show_skeleton = True
        self._play_timer    = QTimer()
        self._play_timer.setInterval(800)
        self._play_timer.timeout.connect(self._playback_tick)

        fname = results.get('original_filename', 'Result')
        self.setMinimumSize(1280, 780)
        self.resize(1440, 860)
        self.setStyleSheet(UPLOAD_BG_STYLE)

        self._open_video()
        self._init_ui()
        self._retranslate_ui()
        self._show_frame(0)

    # ── Video open/close ──────────────────────────────────────────────────────
    def _open_video(self):
        if self._video_path and os.path.exists(self._video_path):
            self._cap = cv2.VideoCapture(self._video_path)

    def _close_video(self):
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    # ── UI ────────────────────────────────────────────────────────────────────
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setSpacing(16)
        outer.setContentsMargins(32, 24, 32, 24)

        outer.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([640, 500])

        outer.addWidget(splitter, stretch=1)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName('header_card')
        card.setStyleSheet(HEADER_CARD_STYLE)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(card)
        row.setContentsMargins(20, 14, 20, 14)
        row.setSpacing(14)

        icon = QLabel('🎬')
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3b82f6, stop:1 #2563eb);
                border-radius: 10px; font-size: 20px;
            }
        """)
        row.addWidget(icon)

        text_col = QVBoxLayout()
        meta = self._results.get('meta', {})

        self._header_title_lbl = QLabel()
        self._header_title_lbl.setFont(QFont('Microsoft JhengHei', 14, QFont.Weight.Bold))
        self._header_title_lbl.setStyleSheet('color: #0f172a;')
        text_col.addWidget(self._header_title_lbl)

        sub_parts = []
        if meta.get('survey_date'): sub_parts.append(meta['survey_date'])
        if meta.get('assessor'):    sub_parts.append(meta['assessor'])
        if meta.get('task_name'):   sub_parts.append(meta['task_name'])
        self._header_sub_lbl = QLabel('  |  '.join(sub_parts) if sub_parts else '')
        self._header_sub_lbl.setStyleSheet('color: #64748b; font-size: 12px;')
        text_col.addWidget(self._header_sub_lbl)

        row.addLayout(text_col)
        row.addStretch()

        self._export_btn = QPushButton()
        self._export_btn.setStyleSheet(EMERALD_BTN_STYLE)
        self._export_btn.setFixedWidth(130)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.clicked.connect(self._export_csv)
        row.addWidget(self._export_btn)

        self._close_btn = QPushButton()
        self._close_btn.setStyleSheet(BACK_BTN_STYLE)
        self._close_btn.setFixedWidth(90)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.close)
        row.addWidget(self._close_btn)

        return card

    # ── Left panel: frame viewer + controls ───────────────────────────────────
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet('background: transparent;')
        col = QVBoxLayout(panel)
        col.setSpacing(12)
        col.setContentsMargins(0, 0, 8, 0)

        # Frame display card
        frame_card = QFrame()
        frame_card.setObjectName('content_card')
        frame_card.setStyleSheet(CONTENT_CARD_STYLE)
        fc_layout = QVBoxLayout(frame_card)
        fc_layout.setContentsMargins(14, 14, 14, 14)
        fc_layout.setSpacing(10)

        self._frame_lbl = QLabel()
        self._frame_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_lbl.setMinimumHeight(340)
        self._frame_lbl.setStyleSheet(
            'background: #1a1a1a; border-radius: 8px; color: #94a3b8; font-size: 14px;'
        )
        fc_layout.addWidget(self._frame_lbl, stretch=1)

        skel_row = QHBoxLayout()
        self._skel_cb = QCheckBox()
        self._skel_cb.setChecked(True)
        self._skel_cb.setStyleSheet('color: #0f172a; font-size: 13px;')
        self._skel_cb.toggled.connect(self._on_skeleton_toggle)
        skel_row.addWidget(self._skel_cb)

        self._no_video_lbl = QLabel()
        self._no_video_lbl.setStyleSheet('color: #94a3b8; font-size: 11px;')
        skel_row.addWidget(self._no_video_lbl)
        skel_row.addStretch()
        fc_layout.addLayout(skel_row)

        col.addWidget(frame_card, stretch=1)

        # Playback controls card
        ctrl_card = QFrame()
        ctrl_card.setObjectName('content_card')
        ctrl_card.setStyleSheet(CONTENT_CARD_STYLE)
        cc = QVBoxLayout(ctrl_card)
        cc.setContentsMargins(14, 12, 14, 12)
        cc.setSpacing(10)

        self._ctrl_title_lbl = QLabel()
        self._ctrl_title_lbl.setFont(QFont('Microsoft JhengHei', 13, QFont.Weight.Bold))
        self._ctrl_title_lbl.setStyleSheet('color: #0f172a;')
        cc.addWidget(self._ctrl_title_lbl)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self._prev_btn = QPushButton()
        self._prev_btn.setStyleSheet(BACK_BTN_STYLE)
        self._prev_btn.clicked.connect(self._prev_frame)
        nav_row.addWidget(self._prev_btn)

        self._play_btn = QPushButton()
        self._play_btn.setStyleSheet(EMERALD_BTN_STYLE)
        self._play_btn.clicked.connect(self._toggle_play)
        nav_row.addWidget(self._play_btn)

        self._next_btn = QPushButton()
        self._next_btn.setStyleSheet(BACK_BTN_STYLE)
        self._next_btn.clicked.connect(self._next_frame)
        nav_row.addWidget(self._next_btn)

        nav_row.addStretch()
        cc.addLayout(nav_row)

        info_row = QHBoxLayout()
        self._frame_counter_lbl = QLabel()
        self._frame_counter_lbl.setStyleSheet('color: #64748b; font-size: 12px;')
        info_row.addWidget(self._frame_counter_lbl)

        self._ts_lbl = QLabel()
        self._ts_lbl.setStyleSheet('color: #64748b; font-size: 12px;')
        info_row.addWidget(self._ts_lbl)

        self._score_badge = QLabel('RULA: —')
        self._score_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_badge.setFixedHeight(24)
        self._score_badge.setStyleSheet(
            'background:#e2e8f0; color:#475569; border-radius:10px;'
            'padding:0 12px; font-size:12px; font-weight:bold;'
        )
        info_row.addWidget(self._score_badge)
        info_row.addStretch()
        cc.addLayout(info_row)

        col.addWidget(ctrl_card)
        return panel

    # ── Right panel: stats + line chart + bar chart ───────────────────────────
    def _build_right_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')

        inner = QWidget()
        inner.setStyleSheet('background: transparent;')
        col = QVBoxLayout(inner)
        col.setSpacing(12)
        col.setContentsMargins(8, 0, 0, 0)

        col.addWidget(self._build_stat_cards())
        col.addWidget(self._build_line_chart_card())
        col.addWidget(self._build_bar_chart_card())
        col.addStretch()

        scroll.setWidget(inner)
        return scroll

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _build_stat_cards(self) -> QFrame:
        card = QFrame()
        card.setObjectName('content_card')
        card.setStyleSheet(CONTENT_CARD_STYLE)
        col = QVBoxLayout(card)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(10)

        self._stat_title_lbl = QLabel()
        self._stat_title_lbl.setFont(QFont('Microsoft JhengHei', 13, QFont.Weight.Bold))
        self._stat_title_lbl.setStyleSheet('color: #0f172a;')
        col.addWidget(self._stat_title_lbl)

        stats = self._results.get('stats', {})
        fps   = self._results.get('fps', 1)
        total = self._results.get('total_frames', 0)
        dur   = total / fps if fps else 0
        valid = sum(1 for r in self._records if isinstance(r.get('best_score'), int))
        invalid = len(self._records) - valid

        # Store value/label pairs so we can update label text on language change
        # Each entry: (value_str, key, text_color, bg_color)
        self._stat_items = [
            (str(total),                          'result_stat_total',    '#1e40af', '#dbeafe'),
            (str(valid),                           'result_stat_valid',    '#065f46', '#d1fae5'),
            (str(invalid),                         'result_stat_invalid',  '#991b1b', '#fee2e2'),
            (f'{dur:.1f} s',                       'result_stat_duration', '#6d28d9', '#ede9fe'),
            (str(stats.get('max_score') or '—'),   'result_stat_max',      '#991b1b', '#fee2e2'),
            (f"{stats.get('avg_score') or '—'}",   'result_stat_avg',      '#92400e', '#fef3c7'),
        ]

        self._stat_label_widgets = []  # keep refs to label QLabels for retranslation
        grid = QGridLayout()
        grid.setSpacing(8)
        for idx, (value, _key, tc, bg) in enumerate(self._stat_items):
            r, c = divmod(idx, 2)
            cell = QFrame()
            cell.setStyleSheet(f'QFrame {{ background:{bg}; border-radius:8px; }}'
                               'QLabel { background:transparent; }')
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(10, 8, 10, 8)
            vl = QLabel(value)
            vl.setFont(QFont('Microsoft JhengHei', 16, QFont.Weight.Bold))
            vl.setStyleSheet(f'color:{tc};')
            vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ll = QLabel()
            ll.setStyleSheet(f'color:{tc}; font-size:11px;')
            ll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(vl)
            cl.addWidget(ll)
            grid.addWidget(cell, r, c)
            self._stat_label_widgets.append(ll)

        col.addLayout(grid)
        return card

    # ── Line chart (click → jump to frame) ───────────────────────────────────
    def _build_line_chart_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName('content_card')
        card.setStyleSheet(CONTENT_CARD_STYLE + 'QLabel { color: #0f172a; }'
                           'QCheckBox { color: #0f172a; }')
        col = QVBoxLayout(card)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)

        hdr = QHBoxLayout()
        self._chart_title_lbl = QLabel()
        self._chart_title_lbl.setFont(QFont('Microsoft JhengHei', 13, QFont.Weight.Bold))
        self._chart_title_lbl.setStyleSheet('color: #0f172a;')
        hdr.addWidget(self._chart_title_lbl)
        hdr.addStretch()
        col.addLayout(hdr)

        xs = [r['timestamp']  for r in self._records if isinstance(r.get('best_score'), int)]
        ys = [r['best_score'] for r in self._records if isinstance(r.get('best_score'), int)]

        self._line_fig, self._line_ax = plt.subplots(figsize=(5.5, 2.8))
        self._line_fig.patch.set_facecolor('#ffffff')
        self._line_ax.set_facecolor('#ffffff')

        if xs and ys:
            self._line_ax.plot(xs, ys, color='#2563eb', linewidth=1.8,
                               marker='o', markersize=5, alpha=0.85, picker=6)
            self._line_ax.fill_between(xs, ys, alpha=0.10, color='#2563eb')
            self._line_ax.axhspan(5, 8, alpha=0.06, color='#ef4444')
            self._line_ax.axhspan(3, 5, alpha=0.06, color='#f59e0b')
            self._line_ax.set_ylim(0.5, 7.5)
            self._line_ax.set_yticks(range(1, 8))

        self._vline = self._line_ax.axvline(x=0, color='#ef4444',
                                             linewidth=1.5, linestyle='--', alpha=0.7)

        self._line_ax.tick_params(colors='#64748b', labelsize=8)
        for spine in self._line_ax.spines.values():
            spine.set_visible(False)
        self._line_ax.yaxis.grid(True, linestyle='--', alpha=0.4, color='#e2e8f0')
        self._line_ax.set_axisbelow(True)
        plt.tight_layout()

        self._line_canvas = FigureCanvas(self._line_fig)
        self._line_canvas.setFixedHeight(220)
        self._line_canvas.mpl_connect('button_press_event', self._on_chart_click)
        col.addWidget(self._line_canvas)

        return card

    # ── Bar chart ─────────────────────────────────────────────────────────────
    def _build_bar_chart_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName('content_card')
        card.setStyleSheet(CONTENT_CARD_STYLE + 'QLabel { color: #0f172a; }')
        col = QVBoxLayout(card)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)

        self._bar_title_lbl = QLabel()
        self._bar_title_lbl.setFont(QFont('Microsoft JhengHei', 13, QFont.Weight.Bold))
        self._bar_title_lbl.setStyleSheet('color: #0f172a;')
        col.addWidget(self._bar_title_lbl)

        dist   = self._results.get('stats', {}).get('score_distribution', {})
        labels = [str(i) for i in range(1, 8)]
        values = [dist.get(str(i), 0) for i in range(1, 8)]
        colors = ['#10b981', '#10b981', '#f59e0b', '#f59e0b',
                  '#ef4444', '#ef4444', '#7c2d12']

        self._bar_fig, self._bar_ax = plt.subplots(figsize=(5, 2.6))
        self._bar_fig.patch.set_facecolor('#ffffff')
        self._bar_ax.set_facecolor('#ffffff')
        self._bar_ax.bar(labels, values, color=colors, width=0.6, edgecolor='none')
        self._bar_ax.tick_params(colors='#64748b', labelsize=8)
        self._bar_ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        for spine in self._bar_ax.spines.values():
            spine.set_visible(False)
        self._bar_ax.yaxis.grid(True, linestyle='--', alpha=0.4, color='#e2e8f0')
        self._bar_ax.set_axisbelow(True)
        plt.tight_layout()

        self._bar_canvas = FigureCanvas(self._bar_fig)
        self._bar_canvas.setFixedHeight(200)
        col.addWidget(self._bar_canvas)

        return card

    # ── Language ──────────────────────────────────────────────────────────────
    def on_language_changed(self, _lang_code):
        self._retranslate_ui()

    def _retranslate_ui(self):
        fname = self._results.get('original_filename', '')
        self.setWindowTitle(f'{fname} {t("result_window_title_suffix")}')

        self._header_title_lbl.setText(
            t('result_header_title_prefix') + fname
        )
        # sub is metadata, stays as-is; but update empty fallback
        if not self._header_sub_lbl.text():
            self._header_sub_lbl.setText(t('result_header_sub_local'))

        self._export_btn.setText(t('result_export_btn'))
        self._close_btn.setText(t('result_close_btn'))

        self._frame_lbl.setText(t('result_no_video_text'))
        self._skel_cb.setText(t('result_skel_checkbox'))
        self._ctrl_title_lbl.setText(t('result_ctrl_title'))

        self._prev_btn.setText(t('result_prev_btn'))
        self._next_btn.setText(t('result_next_btn'))
        # Play/pause button: set based on current state
        if self._play_timer.isActive():
            self._play_btn.setText(t('result_pause_btn'))
        else:
            self._play_btn.setText(t('result_play_btn'))

        # Stat section title
        self._stat_title_lbl.setText(t('result_stat_title'))
        for lbl, (_val, key, _tc, _bg) in zip(self._stat_label_widgets, self._stat_items):
            lbl.setText(t(key))

        # Chart section titles
        self._chart_title_lbl.setText(t('result_chart_title'))
        self._bar_title_lbl.setText(t('result_bar_title'))

        # Update matplotlib axis labels
        self._line_ax.set_xlabel(t('result_chart_x'), fontsize=9, color='#64748b')
        self._line_ax.set_ylabel(t('result_chart_y'), fontsize=9, color='#64748b')
        try:
            self._line_canvas.draw_idle()
        except Exception:
            pass

        self._bar_ax.set_xlabel(t('result_bar_x'), fontsize=9, color='#64748b')
        self._bar_ax.set_ylabel(t('result_bar_y'), fontsize=9, color='#64748b')
        try:
            self._bar_canvas.draw_idle()
        except Exception:
            pass

        # Refresh current frame info labels (without reloading the frame image)
        if self._records:
            rec   = self._records[self._current_idx]
            total = len(self._records)
            self._frame_counter_lbl.setText(
                t('result_frame_counter').format(self._current_idx + 1, total)
            )
            self._ts_lbl.setText(
                t('result_time_label').format(rec.get('timestamp', 0))
            )

    # ── Frame navigation ──────────────────────────────────────────────────────
    def _show_frame(self, idx: int):
        if not self._records:
            return
        idx = max(0, min(idx, len(self._records) - 1))
        self._current_idx = idx
        rec = self._records[idx]

        frame_rgb = None
        if self._cap and self._cap.isOpened():
            frame_rgb = _frame_rgb_from_video(self._cap, rec['frame'])

        if frame_rgb is not None:
            lm2d = rec.get('landmarks_2d')
            if self._show_skeleton and lm2d:
                frame_rgb = _draw_skeleton(frame_rgb, lm2d)
            score = rec.get('best_score')
            txt   = f"RULA: {score if score is not None else 'NULL'}"
            cv2.putText(frame_rgb, txt, (10, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
            cv2.putText(frame_rgb, txt, (10, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0),       1)
            self._display_frame(frame_rgb)
            self._no_video_lbl.setText('')
        else:
            if self._cap is None:
                self._no_video_lbl.setText(t('result_no_video_note'))
            self._frame_lbl.setText(
                f'Frame #{rec.get("frame", idx)}'
                f'\n{t("result_time_label").format(rec.get("timestamp", 0))}'
                f'\nRULA: {rec.get("best_score") or "NULL"}'
            )

        ts    = rec.get('timestamp', 0)
        score = rec.get('best_score')
        total = len(self._records)
        self._frame_counter_lbl.setText(
            t('result_frame_counter').format(idx + 1, total)
        )
        self._ts_lbl.setText(t('result_time_label').format(ts))
        self._update_score_badge(score)

        self._vline.set_xdata([ts, ts])
        try:
            self._line_canvas.draw_idle()
        except Exception:
            pass

    def _display_frame(self, rgb: np.ndarray):
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self._frame_lbl.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._frame_lbl.setPixmap(pix)

    def _update_score_badge(self, score):
        if score is None:
            self._score_badge.setText('RULA: —')
            self._score_badge.setStyleSheet(
                'background:#e2e8f0; color:#475569; border-radius:10px;'
                'padding:0 12px; font-size:12px; font-weight:bold;'
            )
        else:
            bg, fg = _SCORE_COLORS.get(int(score), ('#e2e8f0', '#475569'))
            self._score_badge.setText(f'RULA: {score}')
            self._score_badge.setStyleSheet(
                f'background:{bg}; color:{fg}; border-radius:10px;'
                'padding:0 12px; font-size:12px; font-weight:bold;'
            )

    # ── Controls ──────────────────────────────────────────────────────────────
    def _prev_frame(self):
        self._play_timer.stop()
        self._play_btn.setText(t('result_play_btn'))
        self._show_frame(self._current_idx - 1)

    def _next_frame(self):
        self._play_timer.stop()
        self._play_btn.setText(t('result_play_btn'))
        self._show_frame(self._current_idx + 1)

    def _toggle_play(self):
        if self._play_timer.isActive():
            self._play_timer.stop()
            self._play_btn.setText(t('result_play_btn'))
        else:
            self._play_btn.setText(t('result_pause_btn'))
            self._play_timer.start()

    def _playback_tick(self):
        if self._current_idx >= len(self._records) - 1:
            self._play_timer.stop()
            self._play_btn.setText(t('result_play_btn'))
            return
        self._show_frame(self._current_idx + 1)

    def _on_skeleton_toggle(self, checked: bool):
        self._show_skeleton = checked
        self._show_frame(self._current_idx)

    # ── Chart click → jump to frame ───────────────────────────────────────────
    def _on_chart_click(self, event):
        if event.inaxes is not self._line_ax:
            return
        click_x = event.xdata
        if click_x is None:
            return

        best_dist = float('inf')
        best_idx  = self._current_idx
        for i, rec in enumerate(self._records):
            ts = rec.get('timestamp', 0)
            d  = abs(ts - click_x)
            if d < best_dist:
                best_dist = d
                best_idx  = i

        self._play_timer.stop()
        self._play_btn.setText(t('result_play_btn'))
        self._show_frame(best_idx)

    # ── Export ────────────────────────────────────────────────────────────────
    def _export_csv(self):
        meta = self._results.get('meta', {})
        default = (f"rula_{meta.get('task_name','analysis')}"
                   f"_{meta.get('survey_date','')}.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, t('result_export_dialog_title'), default,
            'CSV Files (*.csv);;All Files (*)'
        )
        if path:
            try:
                export_csv(self._results, path)
                QMessageBox.information(
                    self, t('result_export_success_title'),
                    t('result_export_success_msg').format(path)
                )
            except Exception as e:
                QMessageBox.critical(self, t('result_export_fail_title'), str(e))

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._play_timer.stop()
        self._close_video()
        plt.close(self._line_fig)
        plt.close(self._bar_fig)
        self.back_requested.emit()
        super().closeEvent(event)
