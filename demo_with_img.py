import time
import cv2
from rtmlib import PoseTracker, Wholebody3d, draw_skeleton


def get_screen_size():
    """Return primary screen size (width, height)."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.destroy()
        return width, height
    except Exception:
        # Fallback for environments where Tk is unavailable.
        return 1920, 1080


def resize_to_fit_screen(image, max_ratio=0.9):
    """Fit image into screen by preserving ratio and padding empty area."""
    screen_w, screen_h = get_screen_size()
    max_w = int(screen_w * max_ratio)
    max_h = int(screen_h * max_ratio)

    h, w = image.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    if scale < 1.0:
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        resized = image

    # Put image on a black canvas to avoid any stretch from window ratio differences.
    canvas = cv2.copyMakeBorder(
        resized,
        (max_h - new_h) // 2,
        max_h - new_h - (max_h - new_h) // 2,
        (max_w - new_w) // 2,
        max_w - new_w - (max_w - new_w) // 2,
        borderType=cv2.BORDER_CONSTANT,
        value=(0, 0, 0)
    )
    return canvas

# 1. 設定環境
device = 'cuda'
backend = 'onnxruntime'  # 已確認你的環境支援 CUDA

# 2. 初始化 Wholebody3d Tracker
# 對於單張圖片，det_frequency 設為 1，並關閉 tracking
wholebody3d = PoseTracker(
    Wholebody3d,
    det_frequency=1,
    tracking=False,
    backend=backend,
    device=device
)

# 3. 讀取圖片檔案
img_path = 'demo.jpg'  # 請確保圖片與此腳本在同一目錄下
frame = cv2.imread(img_path)

if frame is None:
    print(f"❌ 錯誤：找不到圖片 {img_path}")
else:
    s = time.time()

    # 4. 進行 3D 姿態推論
    # RTMW 會回傳：3D關鍵點, 分數, SimCC座標, 2D投影座標
    keypoints_3d, scores, keypoints_simcc, keypoints_2d = wholebody3d(frame)

    # 計算推論時間
    det_time = (time.time() - s) * 1000
    print(f"✅ 推論完成！耗時: {det_time:.2f} ms")
    print(f"檢測到人數: {len(keypoints_3d)}")

    # 5. 繪製並顯示結果
    img_show = frame.copy()
    # 我們通常在 2D 圖片上繪製 keypoints_2d 以檢查準確度
    img_show = draw_skeleton(img_show, keypoints_2d, scores, kpt_thr=0.4)

    # 顯示視窗
    window_name = 'RTMW 3D Detection (2D Projection)'
    img_show = resize_to_fit_screen(img_show)
    keep_ratio_flag = getattr(cv2, 'WINDOW_KEEPRATIO', 0)
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | keep_ratio_flag)
    cv2.resizeWindow(window_name, img_show.shape[1], img_show.shape[0])
    cv2.imshow(window_name, img_show)
    
    # 如果你想查看 3D 座標數值 (例如第一個人的第一個點)
    if len(keypoints_3d) > 0:
        print("第一個 3D 座標範例 (x, y, z):", keypoints_3d[0][0])

    print("按任意鍵退出...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()