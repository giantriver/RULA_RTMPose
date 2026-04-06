# RTMPose 與 MediaPipe 骨架繪製方法分析

本文整理目前專案中兩種骨架繪製模式（`RTMW3D` / `MEDIAPIPE`）的實作方式、資料格式，以及程式碼位置。

## 1) 總覽：骨架繪製有兩條路徑

1. 即時模式（Realtime）
- 入口：`FrameProcessorWorker` 逐幀呼叫 `PoseDetector.process_frame()`，再呼叫 `PoseDetector.draw_landmarks()`。
- 特性：直接在當前相機畫面上即時疊加骨架。

2. 離線結果模式（ResultWindow）
- 入口：`VideoFileProcessor` 分析時保存 `native_draw_data` 到 `records`。
- 顯示：`ResultWindow._show_frame()` 讀取歷史 `native_draw_data`，依 `backend` 分派到 MediaPipe 或 RTMW3D 專用繪圖函式。
- 特性：可重播歷史抽樣幀，且盡量用「原生繪圖器」重現當時骨架視覺。

---

## 2) MediaPipe 模式（MEDIAPIPE）

### A. 即時繪製

- 主要函式：`PoseDetector.draw_landmarks()`
- 位置：`src/rula_realtime_app/core/pose_detector.py:434`
- 實作重點：
  - 使用 `self.mp_drawing.draw_landmarks(...)`
  - 連線集為 `self.mp_pose.POSE_CONNECTIONS`
  - 樣式為 `self.mp_drawing_styles.get_default_pose_landmarks_style()`
  - 若 `self.results.pose_landmarks` 為空，直接回傳原圖

對應偵測流程：
- `PoseDetector.process_frame()` 在 MEDIAPIPE 分支呼叫 `self.pose.process(frame)`
- 位置：`src/rula_realtime_app/core/pose_detector.py:243`

### B. 離線結果重播繪製

- 儲存資料：`get_native_draw_data_2d()` 回傳
  - `{'backend': 'MEDIAPIPE', 'landmarks_2d': [[x, y, visibility], ...]}`
- 位置：`src/rula_realtime_app/core/pose_detector.py:362`

- 於離線分析階段保存：
  - `native_draw_data = detector.get_native_draw_data_2d()`
  - 寫入每筆 record 的 `native_draw_data`
- 位置：`src/rula_realtime_app/core/video_file_processor.py:100`

- 重播時繪圖：
  - `ResultWindow._show_frame()` 判斷 `backend == 'MEDIAPIPE'`
  - 呼叫 `_draw_mediapipe_skeleton(frame_rgb, lms)`
- 位置：
  - 分派邏輯：`src/rula_realtime_app/ui/result_window.py:670`
  - MediaPipe 專用繪圖：`src/rula_realtime_app/ui/result_window.py:72`

_draw_mediapipe_skeleton() 的做法：
- 將 `landmarks_2d` 組成 `landmark_pb2.NormalizedLandmarkList`
- 使用 `mp.solutions.drawing_utils.draw_landmarks(...)` 繪製
- 連線為 `mp.solutions.pose.POSE_CONNECTIONS`

---

## 3) RTMPose 模式（RTMW3D）

> 專案中的 RTMPose 路徑以 `RTMW3D` 命名，底層由 `rtmlib` 的 `Wholebody3d / draw_skeleton` 處理。

### A. 即時繪製

- 主要函式：`PoseDetector.draw_landmarks()` 的 RTMW3D 分支
- 位置：`src/rula_realtime_app/core/pose_detector.py:434`
- 實作重點：
  - 先把輸入 RGB 轉成 BGR
  - 呼叫 `self.draw_skeleton(image_bgr, self.last_keypoints_2d, self.last_scores, kpt_thr=...)`
  - 再轉回 RGB 回傳
  - `kpt_thr` 來自 `RTMW3D_CONFIG['kpt_threshold']`（預設 0.3）

對應偵測流程：
- `PoseDetector._process_rtmw3d()` 執行 RTMW3D 推理與單人追蹤選擇
- 位置：`src/rula_realtime_app/core/pose_detector.py:262`

該流程會維持：
- `self.last_keypoints_2d`（像素座標）
- `self.last_scores`（每點信心）
- 供 `draw_landmarks()` 即時繪圖使用

### B. 離線結果重播繪製

- 儲存資料：`get_native_draw_data_2d()` 回傳
  - `{'backend': 'RTMW3D', 'keypoints_2d_norm': [[x, y], ...], 'scores': [conf, ...]}`
- 位置：`src/rula_realtime_app/core/pose_detector.py:362`

- 於離線分析階段序列化後寫入 `records[n]['native_draw_data']`
- 位置：`src/rula_realtime_app/core/video_file_processor.py:100`

- 重播時繪圖：
  - `ResultWindow._show_frame()` 判斷 `backend == 'RTMW3D'`
  - 呼叫 `_draw_rtmw_skeleton(frame_rgb, keypoints_2d_norm, scores, kpt_threshold=0.3)`
- 位置：
  - 分派邏輯：`src/rula_realtime_app/ui/result_window.py:670`
  - RTMW 專用繪圖：`src/rula_realtime_app/ui/result_window.py:101`

_draw_rtmw_skeleton() 的做法：
- 將 normalized 關鍵點轉回像素座標（乘上影像寬高）
- 包成 `kpts_arr` 與 `scores_arr`（shape 為 `[1, K, 2]` / `[1, K]`）
- 轉成 BGR 後呼叫 `rtmlib.draw_skeleton(...)`
- 再轉回 RGB

---

## 4) 模式切換與來源位置

- 離線上傳頁可選兩種後端：
  - `RTMW3D`
  - `MEDIAPIPE`
- 位置：`src/rula_realtime_app/ui/upload_window.py:199`

- 即時流程中，兩種後端最後都透過 `FrameProcessorWorker` 統一呼叫：
  - `self.pose_detector.draw_landmarks(frame)`
- 位置：`src/rula_realtime_app/core/frame_processor.py:145`

---

## 5) 兩者差異摘要

1. 繪圖器來源
- MEDIAPIPE：`mediapipe.solutions.drawing_utils.draw_landmarks`
- RTMW3D：`rtmlib.draw_skeleton`

2. 重播資料格式
- MEDIAPIPE：`landmarks_2d`（33 點，含 visibility）
- RTMW3D：`keypoints_2d_norm + scores`（模型原生點數）

3. 色彩空間處理
- MEDIAPIPE：主要在 RGB 直接畫
- RTMW3D：畫前 RGB->BGR，畫後 BGR->RGB

4. 專案設計意圖
- RULA 計分統一使用 MediaPipe-like 33 點語意
- 但「顯示骨架」保留各自原生繪圖方式，讓視覺表現與各模型輸出一致
