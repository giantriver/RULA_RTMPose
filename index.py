from rtmlib.visualization.skeleton import coco133

def print_rtmw3d_keypoints():
    keypoint_info = coco133["keypoint_info"]  # dict: {index: {"name": ..., "swap": ...}, ...}

    print(f"Total keypoints: {len(keypoint_info)}")
    print("-" * 40)
    print(f"{'index':>5}  {'name'}")
    print("-" * 40)

    for idx in sorted(keypoint_info.keys()):
        name = keypoint_info[idx].get("name", "")
        print(f"{idx:>5}  {name}")

if __name__ == "__main__":
    print_rtmw3d_keypoints()