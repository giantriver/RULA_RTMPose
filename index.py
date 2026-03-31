"""Print all keypoint indexes and names from rtmlib skeleton definitions.

Usage:
  python index.py                # default: coco133 (RTMW/Wholebody3d common)
  python index.py coco17
  python index.py hand21
  python index.py coco25
  python index.py halpe26
  python index.py openpose18
  python index.py openpose134
  python index.py animal17
"""

import sys

from rtmlib.visualization.skeleton import (
    animal17,
    coco17,
    coco25,
    coco133,
    halpe26,
    hand21,
    openpose18,
    openpose134,
)


SKELETONS = {
    "coco17": coco17,
    "coco25": coco25,
    "coco133": coco133,
    "halpe26": halpe26,
    "hand21": hand21,
    "openpose18": openpose18,
    "openpose134": openpose134,
    "animal17": animal17,
}


def main() -> int:
    skeleton_name = sys.argv[1].lower() if len(sys.argv) > 1 else "coco133"

    if skeleton_name not in SKELETONS:
        print(f"Unknown skeleton: {skeleton_name}")
        print("Available:", ", ".join(sorted(SKELETONS.keys())))
        return 1

    skeleton = SKELETONS[skeleton_name]
    keypoint_info = skeleton["keypoint_info"]

    print(f"Skeleton: {skeleton_name}")
    print(f"Total keypoints: {len(keypoint_info)}")
    print("-" * 48)
    print(f"{'index':>5}  {'name':<24}  {'swap':<16}")
    print("-" * 48)

    for idx in sorted(keypoint_info.keys()):
        item = keypoint_info[idx]
        name = item.get("name", "")
        swap = item.get("swap", "")
        print(f"{idx:>5}  {name:<24}  {swap:<16}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
