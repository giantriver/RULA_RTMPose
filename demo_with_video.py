import time
import ctypes
import os
from pathlib import Path
import cv2
import numpy as np
import onnxruntime as ort
from rtmlib import Wholebody3d, draw_skeleton
from rtmlib.tools.solution.pose_tracker import PoseTracker as RTMLibPoseTracker, pose_to_bbox

device = 'cuda'
backend = 'onnxruntime'

# 請依你本機實際安裝版本調整這兩個路徑
cuda_bin_path = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin"
cudnn_bin_path = r"C:\Program Files\NVIDIA\CUDNN\v9.20\bin"


def resolve_cudnn_runtime_dir(cudnn_bin_root: str) -> str:
    """Return the real cuDNN runtime directory that contains cudnn64_9.dll."""
    root = Path(cudnn_bin_root)
    if not root.is_dir():
        raise RuntimeError(f'cuDNN bin 路徑不存在: {cudnn_bin_root}')

    direct_dll = root / 'cudnn64_9.dll'
    if direct_dll.exists():
        return str(root)

    candidates = sorted(root.rglob('cudnn64_9.dll'))
    if not candidates:
        raise RuntimeError(f'找不到 cudnn64_9.dll，請確認安裝完整: {cudnn_bin_root}')

    # Prefer CUDA 12.x branch when available.
    for dll_path in candidates:
        if '12.' in dll_path.as_posix():
            return str(dll_path.parent)

    return str(candidates[0].parent)


def configure_cuda_dll_paths():
    """Register CUDA/cuDNN runtime paths for DLL loading on Windows."""
    cudnn_runtime_dir = resolve_cudnn_runtime_dir(cudnn_bin_path)
    runtime_dirs = [cuda_bin_path, cudnn_runtime_dir]

    for runtime_dir in runtime_dirs:
        if not Path(runtime_dir).is_dir():
            raise RuntimeError(f'CUDA/cuDNN 路徑不存在: {runtime_dir}')

        # For Python 3.8+ on Windows, this is the preferred way for DLL discovery.
        os.add_dll_directory(runtime_dir)

    # Keep PATH updated for subprocesses and libraries that still rely on PATH.
    existing_path = os.environ.get('PATH', '')
    os.environ['PATH'] = ';'.join(runtime_dirs + [existing_path])


def verify_onnxruntime_cuda_dependencies():
    """Fail fast if ONNX Runtime CUDA provider dependencies are not loadable."""
    providers = ort.get_available_providers()
    if 'CUDAExecutionProvider' not in providers:
        raise RuntimeError(
            'ONNX Runtime 沒有 CUDAExecutionProvider。請安裝 onnxruntime-gpu，且版本需對應 CUDA 12 + cuDNN 9。'
        )

    ort_capi_dir = Path(ort.__file__).resolve().parent / 'capi'
    cuda_provider_dll = ort_capi_dir / 'onnxruntime_providers_cuda.dll'
    if not cuda_provider_dll.exists():
        raise RuntimeError(f'找不到 CUDA provider DLL: {cuda_provider_dll}')

    try:
        ctypes.WinDLL(str(cuda_provider_dll))
    except OSError as exc:
        raise RuntimeError(
            'CUDA provider 載入失敗。缺少 CUDA 12 / cuDNN 9 的執行期 DLL（例如 cublasLt64_12.dll、cudnn64_9.dll），或相關路徑未加入 PATH。'
        ) from exc


class PatchedPoseTracker(RTMLibPoseTracker):
    """Fix tracking reorder bug by using detection indices instead of track IDs."""

    def __call__(self, image: np.ndarray):
        pose_model_name = type(self.pose_model).__name__
        keypoints_simcc = None
        keypoints2d = None

        if self.det_model:
            if self.frame_cnt % self.det_frequency == 0:
                try:
                    if self.det_categories or self.det_mode == 'multiclass':
                        if self.det_categories:
                            bboxes, classes = self.det_model(image)
                            bboxes = [
                                bbox for bbox, cls in zip(bboxes, classes)
                                if cls in self.det_categories
                            ]
                        else:
                            bboxes, _ = self.det_model(image)
                    else:
                        bboxes = self.det_model(image)
                except Exception:
                    return [], []
            else:
                bboxes = self.bboxes_last_frame

            if pose_model_name == 'RTMPose3d':
                keypoints, scores, keypoints_simcc, keypoints2d = self.pose_model(
                    image, bboxes=bboxes)
            else:
                keypoints, scores = self.pose_model(image, bboxes=bboxes)
        else:
            keypoints, scores = self.pose_model(image)

        if not self.tracking and self.det_frequency != 1:
            bboxes_current_frame = []
            if pose_model_name == 'RTMPose3d':
                for kpts in keypoints2d:
                    bboxes_current_frame.append(pose_to_bbox(kpts))
            else:
                for kpts in keypoints:
                    bboxes_current_frame.append(pose_to_bbox(kpts))
        else:
            if len(self.track_ids_last_frame) == 0:
                self.next_id = len(self.bboxes_last_frame)
                self.track_ids_last_frame = list(range(self.next_id))

            bboxes_current_frame = []
            track_ids_current_frame = []
            matched_indices = []

            for det_idx, kpts in enumerate(keypoints):
                bbox = pose_to_bbox(kpts)
                track_id, _ = self.track_by_iou(bbox)

                if track_id > -1:
                    matched_indices.append(det_idx)
                    track_ids_current_frame.append(track_id)
                    bboxes_current_frame.append(bbox)

            self.track_ids_last_frame = track_ids_current_frame

            keypoints = np.asarray(keypoints)
            scores = np.asarray(scores)
            if matched_indices:
                keypoints = keypoints[matched_indices]
                scores = scores[matched_indices]
                if pose_model_name == 'RTMPose3d':
                    keypoints2d = np.asarray(keypoints2d)[matched_indices]
                    keypoints_simcc = np.asarray(keypoints_simcc)[matched_indices]
            else:
                keypoints = keypoints[:0]
                scores = scores[:0]
                if pose_model_name == 'RTMPose3d':
                    keypoints2d = np.asarray(keypoints2d)[:0]
                    keypoints_simcc = np.asarray(keypoints_simcc)[:0]

        self.bboxes_last_frame = bboxes_current_frame
        self.frame_cnt += 1

        if pose_model_name == 'RTMPose3d':
            return keypoints, scores, keypoints_simcc, keypoints2d

        return keypoints, scores


def bbox_from_keypoints_2d(kpts_2d: np.ndarray) -> np.ndarray:
    """Convert one person's 2D keypoints to bbox [x1, y1, x2, y2]."""
    x = kpts_2d[:, 0]
    y = kpts_2d[:, 1]
    return np.array([x.min(), y.min(), x.max(), y.max()], dtype=np.float32)


def bbox_iou_xyxy(box_a: np.ndarray, box_b: np.ndarray) -> float:
    """Compute IoU for bboxes in [x1, y1, x2, y2]."""
    x1 = max(float(box_a[0]), float(box_b[0]))
    y1 = max(float(box_a[1]), float(box_b[1]))
    x2 = min(float(box_a[2]), float(box_b[2]))
    y2 = min(float(box_a[3]), float(box_b[3]))

    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, float(box_a[2] - box_a[0])) * max(0.0, float(box_a[3] - box_a[1]))
    area_b = max(0.0, float(box_b[2] - box_b[0])) * max(0.0, float(box_b[3] - box_b[1]))
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def select_single_target(keypoints_2d, scores, last_target_bbox, iou_thr=0.05):
    """Keep only one target to avoid switching to wrong detections."""
    if keypoints_2d is None:
        return [], [], last_target_bbox

    keypoints_2d = np.asarray(keypoints_2d)
    scores = np.asarray(scores)
    if keypoints_2d.ndim < 3 or len(keypoints_2d) == 0:
        return [], [], last_target_bbox

    candidate_bboxes = np.asarray([bbox_from_keypoints_2d(kpts) for kpts in keypoints_2d])
    candidate_areas = (candidate_bboxes[:, 2] - candidate_bboxes[:, 0]) * (candidate_bboxes[:, 3] - candidate_bboxes[:, 1])
    candidate_scores = np.asarray([float(np.mean(s)) for s in scores])

    if last_target_bbox is None:
        # 初始化時偏好「分數高且框大」的人。
        rank = candidate_scores * np.sqrt(np.maximum(candidate_areas, 1.0))
        best_idx = int(np.argmax(rank))
    else:
        ious = np.asarray([bbox_iou_xyxy(b, last_target_bbox) for b in candidate_bboxes])
        best_iou_idx = int(np.argmax(ious))

        if ious[best_iou_idx] >= iou_thr:
            best_idx = best_iou_idx
        else:
            # 若 IoU 太小，改用中心點距離做次佳關聯，避免短暫形變導致丟目標。
            target_center = np.array([
                (last_target_bbox[0] + last_target_bbox[2]) * 0.5,
                (last_target_bbox[1] + last_target_bbox[3]) * 0.5,
            ])
            centers = np.stack([
                (candidate_bboxes[:, 0] + candidate_bboxes[:, 2]) * 0.5,
                (candidate_bboxes[:, 1] + candidate_bboxes[:, 3]) * 0.5,
            ], axis=1)
            dists = np.linalg.norm(centers - target_center, axis=1)
            best_idx = int(np.argmin(dists))

    selected_keypoints_2d = keypoints_2d[best_idx:best_idx + 1]
    selected_scores = scores[best_idx:best_idx + 1]
    updated_bbox = candidate_bboxes[best_idx]
    return selected_keypoints_2d, selected_scores, updated_bbox


configure_cuda_dll_paths()
verify_onnxruntime_cuda_dependencies()

# --- 修改處：將 0 改為你的影片路徑 ---
video_path = 'demo.mp4' 
cap = cv2.VideoCapture(video_path)

# 檢查影片是否成功開啟
if not cap.isOpened():
    print(f"無法開啟影片檔案: {video_path}")
    exit()

wholebody3d = PatchedPoseTracker(Wholebody3d,
                          det_frequency=1,
                          tracking=True,
                          backend=backend,
                          device=device)

# 診斷 2-value 回傳來源：偵測失敗或 tracking 重排失敗
two_value_reason_counts = {
    'detection_failed': 0,
    'tracking_reorder_failed': 0,
}

# 單目標鎖定狀態：讓多人或誤檢場景下，盡量持續追同一個人。
target_bbox = None

while cap.isOpened():
    success, frame = cap.read()
    
    # 如果影片讀取結束或失敗，跳出迴圈
    if not success:
        print("影片播放結束或讀取失敗。")
        break
        
    start_time = time.time()

    # 推理（RTMPose3d 正常回傳 4 個值；tracking 邊界情況可能只回傳 2 個值）
    result = wholebody3d(frame)
    if isinstance(result, tuple) and len(result) == 4:
        keypoints, scores, _, keypoints_2d = result
    elif isinstance(result, tuple) and len(result) == 2:
        keypoints, scores = result
        # rtmlib 0.0.15 的 __call__ 裡，偵測例外路徑會直接 return [], []。
        # 若是非空 keypoints/scores 卻只回傳 2 值，通常是 tracking 重排索引失敗後提前 return。
        if len(keypoints) == 0 and len(scores) == 0:
            two_value_reason_counts['detection_failed'] += 1
            print(
                f"[WARN] 2-value 回傳（推測：偵測階段失敗）"
                f" det_fail={two_value_reason_counts['detection_failed']},"
                f" track_fail={two_value_reason_counts['tracking_reorder_failed']}"
            )
        else:
            two_value_reason_counts['tracking_reorder_failed'] += 1
            print(
                f"[WARN] 2-value 回傳（推測：tracking 重排失敗）"
                f" det_fail={two_value_reason_counts['detection_failed']},"
                f" track_fail={two_value_reason_counts['tracking_reorder_failed']}"
            )
        # Some tracking branches return only keypoints/scores; use XY from keypoints as 2D fallback.
        keypoints_2d = keypoints[..., :2] if hasattr(keypoints, 'ndim') and keypoints.ndim >= 3 and keypoints.shape[-1] >= 2 else []
    else:
        raise RuntimeError(f'PoseTracker 回傳格式異常: {type(result)} / len={len(result) if isinstance(result, tuple) else "N/A"}')

    keypoints_2d, scores, target_bbox = select_single_target(
        keypoints_2d, scores, target_bbox)

    # 計算並顯示 FPS
    end_time = time.time()
    fps = 1 / (end_time - start_time)
    
    img_show = frame.copy()
    if len(keypoints_2d) > 0:
        img_show = draw_skeleton(img_show, keypoints_2d, scores, kpt_thr=0.3)

    # 在畫面上印出 FPS
    cv2.putText(img_show, f"FPS: {fps:.2f}", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow('RTMW 3D Video Demo', img_show)
    
    # 按下 'q' 鍵可以提早結束
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()