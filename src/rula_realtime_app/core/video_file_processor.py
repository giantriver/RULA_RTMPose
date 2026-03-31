"""
影片檔案處理器 - 在背景執行緒中對影片檔案進行 RULA 離線分析
"""

import cv2
import csv
import json
import os
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from .pose_detector import PoseDetector
from . import angle_calc
from .utils import get_best_rula_score
from .config import RULA_CONFIG


class VideoFileProcessor(QObject):
    """
    離線影片 RULA 分析工作器（在 QThread 中執行）

    Signals:
        progress_updated(int, str): 進度百分比 + 狀態訊息
        frame_preview(np.ndarray): 目前處理的畫面（RGB）
        analysis_complete(dict): 完整分析結果
        error_occurred(str): 錯誤訊息
    """

    progress_updated = pyqtSignal(int, str)
    frame_preview    = pyqtSignal(object)   # np.ndarray
    analysis_complete = pyqtSignal(dict)
    error_occurred   = pyqtSignal(str)

    def __init__(self, video_path: str, meta: dict,
                 frame_interval: int = 10,
                 backend_mode: str = 'RTMW3D'):
        """
        Args:
            video_path:     影片檔案路徑
            meta:           調查資訊 dict（survey_date, assessor, organization, task_name）
            frame_interval: 每隔幾幀取樣一次（預設 10）
            backend_mode:   姿勢偵測模式（'RTMW3D' 或 'MEDIAPIPE'）
        """
        super().__init__()
        self.video_path     = video_path
        self.meta           = meta
        self.frame_interval = max(1, frame_interval)
        self.backend_mode   = backend_mode
        self._cancelled     = False

    def cancel(self):
        """請求取消處理"""
        self._cancelled = True

    @pyqtSlot()
    def run(self):
        """主處理流程（由 QThread.started 觸發）"""
        try:
            self._process()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))

    # ------------------------------------------------------------------
    def _process(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            self.error_occurred.emit(f'無法開啟影片檔案：{self.video_path}')
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0

        self.progress_updated.emit(3, '初始化姿勢偵測模型...')

        detector   = PoseDetector(backend_mode=self.backend_mode)
        prev_left  = None
        prev_right = None
        records    = []
        frame_idx  = 0
        preview_every = max(1, self.frame_interval * 5)  # 每 5 個取樣幀更新一次預覽

        while not self._cancelled:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % self.frame_interval == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                detected = detector.process_frame(rgb)

                rula_left  = None
                rula_right = None

                img_landmarks_2d = None
                if detected:
                    landmarks_arr    = detector.get_landmarks_array()
                    img_landmarks_2d = detector.get_image_landmarks_2d()
                    rula_left, rula_right = angle_calc(
                        landmarks_arr, prev_left, prev_right
                    )
                    prev_left  = rula_left
                    prev_right = rula_right

                    # 偶爾發送預覽畫面
                    if frame_idx % preview_every == 0:
                        annotated = detector.draw_landmarks(rgb.copy())
                        self.frame_preview.emit(annotated)

                best_result = get_best_rula_score(rula_left, rula_right)
                score_str   = best_result.get('final_tableC_score', 'NULL')
                score_num   = None
                try:
                    if score_str != 'NULL':
                        score_num = int(score_str)
                except (ValueError, TypeError):
                    pass

                records.append({
                    'frame':             frame_idx,
                    'timestamp':         round(frame_idx / fps, 3),
                    'best_score':        score_num,
                    'left_score':        rula_left.get('score', 'NULL')  if rula_left  else 'NULL',
                    'right_score':       rula_right.get('score', 'NULL') if rula_right else 'NULL',
                    # 2D 正規化座標（供結果頁骨架繪製）；不存入 JSON 歷史
                    'landmarks_2d':      img_landmarks_2d,
                })

                # 進度（5% ~ 95%）
                pct = int((frame_idx / total_frames) * 90) + 5
                self.progress_updated.emit(
                    min(pct, 94),
                    f'分析中… 第 {frame_idx} / {total_frames} 幀'
                )

            frame_idx += 1

        cap.release()

        if self._cancelled:
            return

        self.progress_updated.emit(97, '統計資料中...')
        results = self._build_results(records, total_frames, fps)
        self.progress_updated.emit(100, '分析完成！')
        self.analysis_complete.emit(results)

    # ------------------------------------------------------------------
    def _build_results(self, records: list, total_frames: int, fps: float) -> dict:
        valid_scores = [r['best_score'] for r in records
                        if isinstance(r['best_score'], int)]

        dist = {str(i): 0 for i in range(1, 8)}
        for s in valid_scores:
            k = str(max(1, min(7, s)))
            dist[k] = dist.get(k, 0) + 1

        return {
            'meta':             self.meta,
            'video_path':       self.video_path,
            'original_filename': os.path.basename(self.video_path),
            'total_frames':     total_frames,
            'processed_frames': len(records),
            'fps':              fps,
            'frame_interval':   self.frame_interval,
            'rula_params':      dict(RULA_CONFIG),
            'records':          records,
            'stats': {
                'max_score':          max(valid_scores)  if valid_scores else None,
                'avg_score':          round(sum(valid_scores) / len(valid_scores), 2)
                                      if valid_scores else None,
                'score_distribution': dist,
            },
            'created_at': datetime.now().isoformat(),
        }


# ------------------------------------------------------------------
# 本機歷史記錄存取
# ------------------------------------------------------------------
HISTORY_DIR = os.path.join(os.path.expanduser('~'), '.rula_analyses')


def ensure_history_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def save_analysis(results: dict) -> str:
    """將分析結果儲存為 JSON，回傳檔案路徑（landmarks_2d 不存入）"""
    import copy
    ensure_history_dir()
    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = os.path.basename(results.get('video_path', 'unknown'))
    safe = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in name)[:40]
    path = os.path.join(HISTORY_DIR, f'{ts}_{safe}.json')

    # Deep-copy and strip non-serialisable landmark data
    serialisable = copy.deepcopy(results)
    for rec in serialisable.get('records', []):
        rec.pop('landmarks_2d', None)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(serialisable, f, ensure_ascii=False, indent=2)
    return path


def load_history() -> list:
    """載入所有歷史分析記錄（最新優先）"""
    ensure_history_dir()
    items = []
    for fname in sorted(os.listdir(HISTORY_DIR), reverse=True):
        if fname.endswith('.json'):
            fpath = os.path.join(HISTORY_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['_json_path'] = fpath
                items.append(data)
            except Exception:
                pass
    return items


def export_csv(results: dict, csv_path: str):
    """將分析記錄匯出為 CSV"""
    records = results.get('records', [])
    if not records:
        return
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['frame', 'timestamp',
                                               'best_score', 'left_score', 'right_score'])
        writer.writeheader()
        writer.writerows(records)
