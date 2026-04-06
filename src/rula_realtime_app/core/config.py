"""
配置檔案 - 集中管理所有設定參數
"""

import os
import numpy as np

# === 數據源選擇 ===
# 相機模式：
# - "WEBCAM": 一般網路攝影機 + MediaPipe
# - "KINECT": Azure Kinect + Body Tracking
# - "KINECT_RGB": Kinect RGB + MediaPipe
# - "RTMW3D": 一般網路攝影機 + RTMW3D
CAMERA_MODE = "RTMW3D"  # 可選: "WEBCAM", "KINECT", "KINECT_RGB", "RTMW3D"

# 一般網路攝影機索引
WEBCAM_INDEX = 0

# === 顯示模式選擇 ===
DISPLAY_MODE = "RULA"  # "RULA": 顯示RULA評估分數; "COORDINATES": 顯示關鍵點坐標

# === Azure Kinect SDK 配置 ===
# 根據你的安裝路徑修改以下配置
KINECT_SDK_PATH = r"C:\Program Files\Azure Kinect SDK v1.4.1\sdk\windows-desktop\amd64\release\bin"
KINECT_BODY_TRACKING_PATH = r"C:\Program Files\Azure Kinect Body Tracking SDK\tools"

# Kinect 設備配置
KINECT_RESOLUTION = "1080P"  # 可選: 720P, 1080P, 1440P, 1536P, 2160P, 3072P
KINECT_DEPTH_MODE = "WFOV_2x2BINNED"  # 可選: NFOV_2x2BINNED, NFOV_UNBINNED, WFOV_2x2BINNED, WFOV_UNBINNED


def resolve_kinect_color_resolution(pykinect_module, resolution_name=None):
    """依設定字串回傳 pykinect 的 color_resolution enum。"""
    mapping = {
        "720P": pykinect_module.K4A_COLOR_RESOLUTION_720P,
        "1080P": pykinect_module.K4A_COLOR_RESOLUTION_1080P,
        "1440P": pykinect_module.K4A_COLOR_RESOLUTION_1440P,
        "1536P": pykinect_module.K4A_COLOR_RESOLUTION_1536P,
        "2160P": pykinect_module.K4A_COLOR_RESOLUTION_2160P,
        "3072P": pykinect_module.K4A_COLOR_RESOLUTION_3072P,
    }
    key = (resolution_name or KINECT_RESOLUTION)
    return mapping.get(key, pykinect_module.K4A_COLOR_RESOLUTION_1080P)


def resolve_kinect_depth_mode(pykinect_module, depth_mode_name=None):
    """依設定字串回傳 pykinect 的 depth_mode enum。"""
    mapping = {
        "NFOV_2x2BINNED": pykinect_module.K4A_DEPTH_MODE_NFOV_2X2BINNED,
        "NFOV_UNBINNED": pykinect_module.K4A_DEPTH_MODE_NFOV_UNBINNED,
        "WFOV_2x2BINNED": pykinect_module.K4A_DEPTH_MODE_WFOV_2X2BINNED,
        "WFOV_UNBINNED": pykinect_module.K4A_DEPTH_MODE_WFOV_UNBINNED,
    }
    key = (depth_mode_name or KINECT_DEPTH_MODE)
    return mapping.get(key, pykinect_module.K4A_DEPTH_MODE_WFOV_2X2BINNED)

def load_kinect_libraries():
    """載入 Azure Kinect SDK 和 Body Tracking SDK DLLs"""
    if os.path.exists(KINECT_SDK_PATH):
        os.add_dll_directory(KINECT_SDK_PATH)
    else:
        print(f"警告: Kinect SDK 路徑不存在: {KINECT_SDK_PATH}")
    
    if os.path.exists(KINECT_BODY_TRACKING_PATH):
        os.add_dll_directory(KINECT_BODY_TRACKING_PATH)
    else:
        print(f"警告: Kinect Body Tracking SDK 路徑不存在: {KINECT_BODY_TRACKING_PATH}")

# RULA 固定參數設定
RULA_CONFIG = {
    'wrist_twist': 1,        # 手腕扭轉參數
    'legs': 2,               # 腿部姿勢參數
    'muscle_use_a': 0,         # Table A 肌肉使用參數
    'muscle_use_b': 0,         # Table B 肌肉使用參數
    'force_load_a': 0,       # Table A 負荷力量參數
    'force_load_b': 0,       # Table B 負荷力量參數
}

# 角度計算參數
TOLERANCE_ANGLE = 5.0        # 容忍角度（度）
MIN_CONFIDENCE = 0.5         # 最小置信度閾值
USE_PREVIOUS_FRAME_ON_LOW_CONFIDENCE = False  # 低置信度處理策略

# MediaPipe 設定（即時辨識優化）
MEDIAPIPE_CONFIG = {
    'static_image_mode': False,
    'model_complexity': 0,      # 改為 0（最輕量模型，提升速度）
    'smooth_landmarks': True,
    'enable_segmentation': False,
    'smooth_segmentation': False,  # 關閉分割功能
    'min_detection_confidence': 0.5,
    'min_tracking_confidence': 0.5
}

# RTMW3D 設定（使用一般網路攝影機）
RTMW3D_CONFIG = {
    'backend': 'onnxruntime',
    'device': 'cuda',         # 若 CUDA 不可用，程式會自動降級為 CPU
    'det_frequency': 1,     # 每 10 幀才跑一次人體偵測，其餘幀用 tracking（大幅提升 FPS）
    'tracking': False,         # 開啟 tracking 搭配高 det_frequency 才有意義
    'iou_threshold': 0.05,    # 單目標鎖定 IoU 閾值
    'kpt_threshold': 0.3      # 繪製骨架閾值
}

# RTMW（COCO-WholeBody 133）關鍵點索引（只列出 RULA 需要的點）
RTMW = {
    "NOSE": 0,
    "LEFT_EAR": 3,
    "RIGHT_EAR": 4,
    "LEFT_SHOULDER": 5,
    "RIGHT_SHOULDER": 6,
    "LEFT_ELBOW": 7,
    "RIGHT_ELBOW": 8,
    "LEFT_WRIST": 9,
    "RIGHT_WRIST": 10,
    "LEFT_HIP": 11,
    "RIGHT_HIP": 12,
}

# 將 RTMW 索引映射到 MediaPipe Pose 33 索引
# RULA 核心使用的是 MediaPipe 33 點語意，故 RTMW3D 先轉成相同格式。
RTMW_TO_MEDIAPIPE = {
    0: RTMW["NOSE"],
    7: RTMW["LEFT_EAR"],
    8: RTMW["RIGHT_EAR"],
    11: RTMW["LEFT_SHOULDER"],
    12: RTMW["RIGHT_SHOULDER"],
    13: RTMW["LEFT_ELBOW"],
    14: RTMW["RIGHT_ELBOW"],
    15: RTMW["LEFT_WRIST"],
    16: RTMW["RIGHT_WRIST"],
    17: RTMW["LEFT_WRIST"],   # pinky 代理點
    18: RTMW["RIGHT_WRIST"],  # pinky 代理點
    19: RTMW["LEFT_WRIST"],   # index 代理點
    20: RTMW["RIGHT_WRIST"],  # index 代理點
    23: RTMW["LEFT_HIP"],
    24: RTMW["RIGHT_HIP"],
}


def convert_indexed_keypoints_to_pose33(keypoints_xyz, keypoint_scores, index_map):
    """
    通用索引轉換機制：將任意來源關鍵點陣列轉為 MediaPipe-like 33 點格式。

    Args:
        keypoints_xyz: 來源關鍵點，shape 約為 [K, 3+]，至少包含 x, y, z。
        keypoint_scores: 來源分數，shape 約為 [K]。
        index_map: 目標索引 -> 來源索引 的映射字典。

    Returns:
        list: 33 個關鍵點，每個為 [x, y, z, conf]
    """
    pose = [[0.0, 0.0, 0.0, 0.0] for _ in range(33)]

    if keypoints_xyz is None:
        return pose

    kpts = np.asarray(keypoints_xyz)
    if kpts.ndim != 2 or kpts.shape[1] < 3:
        return pose

    if keypoint_scores is None:
        scores = np.ones((kpts.shape[0],), dtype=np.float32)
    else:
        scores = np.asarray(keypoint_scores).reshape(-1)

    for dst_idx, src_idx in index_map.items():
        if src_idx >= kpts.shape[0]:
            continue

        x, y, z = kpts[src_idx][:3]
        conf = float(scores[src_idx]) if src_idx < scores.shape[0] else 0.0
        conf = max(0.0, min(1.0, conf))

        pose[dst_idx] = [float(x), float(y), float(z), conf]

    return pose

# === Azure Kinect 關節映射 (新增) ===
# Azure Kinect joint indices (K4ABT)
K4ABT = {
    "PELVIS": 0,
    "SPINE_NAVAL": 1,
    "SPINE_CHEST": 2,
    "NECK": 3,
    "CLAVICLE_LEFT": 4,
    "SHOULDER_LEFT": 5,
    "ELBOW_LEFT": 6,
    "WRIST_LEFT": 7,
    "HAND_LEFT": 8,
    "HANDTIP_LEFT": 9,
    "THUMB_LEFT": 10,
    "CLAVICLE_RIGHT": 11,
    "SHOULDER_RIGHT": 12,
    "ELBOW_RIGHT": 13,
    "WRIST_RIGHT": 14,
    "HAND_RIGHT": 15,
    "HANDTIP_RIGHT": 16,
    "THUMB_RIGHT": 17,
    "HIP_LEFT": 18,
    "KNEE_LEFT": 19,
    "ANKLE_LEFT": 20,
    "FOOT_LEFT": 21,
    "HIP_RIGHT": 22,
    "KNEE_RIGHT": 23,
    "ANKLE_RIGHT": 24,
    "FOOT_RIGHT": 25,
    "HEAD": 26,
    "NOSE": 27,
    "EYE_LEFT": 28,
    "EAR_LEFT": 29,
    "EYE_RIGHT": 30,
    "EAR_RIGHT": 31,
}

# Map Azure Kinect joints into a MediaPipe-like pose array (33 entries, each [x, y, z, conf]).
# Only the indices used by rula_calculator need to be populated; others stay zeros.
KINECT_TO_MEDIAPIPE = {
    0: K4ABT["NOSE"],          # NOSE
    7: K4ABT["EAR_LEFT"],      # LEFT EAR
    8: K4ABT["EAR_RIGHT"],     # RIGHT EAR
    11: K4ABT["SHOULDER_LEFT"],
    12: K4ABT["SHOULDER_RIGHT"],
    13: K4ABT["ELBOW_LEFT"],
    14: K4ABT["ELBOW_RIGHT"],
    15: K4ABT["WRIST_LEFT"],
    16: K4ABT["WRIST_RIGHT"],
    # Use thumb as pinky proxy and handtip as index proxy to satisfy hand center calc.
    17: K4ABT["HAND_LEFT"],   # LEFT WRIST (equivlalent mid point calculations later)
    18: K4ABT["HAND_RIGHT"],  # RIGHT WRIST (equivalent mid point calc later)
    19: K4ABT["HAND_LEFT"],   # LEFT WRIST (equivalent mid point calc later)
    20: K4ABT["HAND_RIGHT"],  # RIGHT WRIST (equivalent mid point calc later)
    23: K4ABT["HIP_LEFT"],
    24: K4ABT["HIP_RIGHT"],
}
