"""
pose_image_2d_3d.py
===================
輸入一張圖片，輸出兩張圖片：
  1) 2D 骨架疊加在原圖
  2) 3D 世界座標骨架圖

用法：
  python tools/pose_image_2d_3d.py --input <image_path>
  python tools/pose_image_2d_3d.py --input demo.jpg --out2d demo_2d.png --out3d demo_3d.png
"""

import argparse
import importlib.util
from io import BytesIO
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# ---------------------------------------------------------------------------
# 載入 backend/app 模組（避免觸發 app/__init__.py 的 Flask 初始化）
# ---------------------------------------------------------------------------
THIS_FILE = Path(__file__).resolve()
APP_DIR = THIS_FILE.parent.parent / "app"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pose_mod = _load_module("pose_detector_local", APP_DIR / "pose_detector.py")
_cfg_mod = _load_module("video_config_local", APP_DIR / "video_config.py")

VideoFramePoseDetector = _pose_mod.VideoFramePoseDetector
MEDIAPIPE_CONFIG = _cfg_mod.MEDIAPIPE_CONFIG


# ---------------------------------------------------------------------------
# MediaPipe 骨架連線定義（BlazePose 33 keypoints）
# ---------------------------------------------------------------------------
_CONNECTIONS = [
    # 頭部
    (0, 1, "cyan"),
    (1, 2, "cyan"),
    (2, 3, "cyan"),
    (3, 7, "cyan"),
    (0, 4, "cyan"),
    (4, 5, "cyan"),
    (5, 6, "cyan"),
    (6, 8, "cyan"),
    (9, 10, "cyan"),
    # 軀幹
    (11, 12, "yellow"),
    (11, 23, "yellow"),
    (12, 24, "yellow"),
    (23, 24, "yellow"),
    # 左臂（藍）
    (11, 13, "blue"),
    (13, 15, "blue"),
    (15, 17, "blue"),
    (15, 19, "blue"),
    (15, 21, "blue"),
    (17, 19, "blue"),
    # 右臂（紅）
    (12, 14, "red"),
    (14, 16, "red"),
    (16, 18, "red"),
    (16, 20, "red"),
    (16, 22, "red"),
    (18, 20, "red"),
    # 左腿（藍）
    (23, 25, "blue"),
    (25, 27, "blue"),
    (27, 29, "blue"),
    (27, 31, "blue"),
    (29, 31, "blue"),
    # 右腿（紅）
    (24, 26, "red"),
    (26, 28, "red"),
    (28, 30, "red"),
    (28, 32, "red"),
    (30, 32, "red"),
]


def render_3d_skeleton(world_lm: np.ndarray, width: int, height: int) -> np.ndarray:
    """
    world_lm: shape (33, 4) [x, y, z, visibility]
    回傳 BGR numpy array，大小 (height, width, 3)
    """
    dpi = 100
    fig_w = width / dpi
    fig_h = height / dpi

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor="#1a1a2e")
    ax = fig.add_subplot(111, projection="3d", facecolor="#1a1a2e")

    xs, ys, zs, vs = world_lm[:, 0], world_lm[:, 1], world_lm[:, 2], world_lm[:, 3]

    for i, j, color in _CONNECTIONS:
        if vs[i] > 0.3 and vs[j] > 0.3:
            ax.plot(
                [xs[i], xs[j]],
                [zs[i], zs[j]],
                [-ys[i], -ys[j]],
                color=color,
                linewidth=2,
                alpha=0.85,
            )

    norm = plt.Normalize(0.0, 1.0)
    cmap = plt.cm.cool
    for k in range(33):
        if vs[k] > 0.3:
            c = cmap(norm(vs[k]))
            ax.scatter(xs[k], zs[k], -ys[k], color=c, s=18, zorder=5, depthshade=False)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.05, fraction=0.03, shrink=0.6)
    cbar.set_label("Joint Confidence", color="white", fontsize=7)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white", fontsize=6)
    cbar.set_ticks([0.0, 0.5, 1.0])
    cbar.set_ticklabels(["Low", "0.5", "High"])

    for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
        axis.label.set_color("white")
        axis.set_tick_params(colors="white", labelsize=6)
        axis.pane.fill = False
        axis.pane.set_edgecolor("#444466")
        axis._axinfo["grid"]["color"] = "#333355"

    ax.set_xlabel("X-AXIS", fontsize=7, color="white")
    ax.set_ylabel("Z-AXIS", fontsize=7, color="white")
    ax.set_zlabel("Y-AXIS", fontsize=7, color="white")

    ax.set_xlim(-0.6, 0.6)
    ax.set_ylim(-0.6, 0.6)
    ax.set_zlim(-1.2, 0.4)
    ax.view_init(elev=10, azim=-70)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=dpi)
    plt.close(fig)
    buf.seek(0)

    arr = np.frombuffer(buf.getvalue(), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return cv2.resize(img, (width, height))


def blank_3d(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(
        img,
        "No pose detected",
        (max(10, width // 8), height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (120, 120, 120),
        2,
    )
    return img


def process_image(input_path: Path, out2d_path: Path, out3d_path: Path) -> None:
    bgr = cv2.imread(str(input_path))
    if bgr is None:
        raise RuntimeError(f"無法讀取圖片：{input_path}")

    h, w = bgr.shape[:2]

    cfg = dict(MEDIAPIPE_CONFIG)
    detector = VideoFramePoseDetector(cfg)

    import mediapipe as mp

    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
    mp_pose = mp.solutions.pose

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    has_pose = detector.process_frame(rgb)

    out2d = bgr.copy()
    if has_pose and detector.results.pose_landmarks:
        mp_drawing.draw_landmarks(
            out2d,
            detector.results.pose_landmarks,
            mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
        )
    else:
        cv2.putText(
            out2d,
            "No pose detected",
            (max(10, w // 20), max(30, h // 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            2,
        )

    world_lm_list = detector.get_world_landmarks_array()
    if world_lm_list is not None:
        world_arr = np.asarray(world_lm_list, dtype=np.float64)
        out3d = render_3d_skeleton(world_arr, w, h)
    else:
        out3d = blank_3d(w, h)

    out2d_path.parent.mkdir(parents=True, exist_ok=True)
    out3d_path.parent.mkdir(parents=True, exist_ok=True)

    if not cv2.imwrite(str(out2d_path), out2d):
        raise RuntimeError(f"無法寫入 2D 圖片：{out2d_path}")
    if not cv2.imwrite(str(out3d_path), out3d):
        raise RuntimeError(f"無法寫入 3D 圖片：{out3d_path}")

    print(f"完成！\n2D 輸出：{out2d_path}\n3D 輸出：{out3d_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="輸入單張圖片，輸出 2D 骨架圖與 3D 骨架圖")
    parser.add_argument("--input", "-i", required=True, help="輸入圖片路徑")
    parser.add_argument("--out2d", default=None, help="2D 輸出路徑（預設：<input>_2d.png）")
    parser.add_argument("--out3d", default=None, help="3D 輸出路徑（預設：<input>_3d.png）")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        parser.error(f"找不到輸入檔案：{input_path}")

    if args.out2d:
        out2d_path = Path(args.out2d).resolve()
    else:
        out2d_path = input_path.with_name(f"{input_path.stem}_2d.png")

    if args.out3d:
        out3d_path = Path(args.out3d).resolve()
    else:
        out3d_path = input_path.with_name(f"{input_path.stem}_3d.png")

    process_image(input_path, out2d_path, out3d_path)


if __name__ == "__main__":
    main()
