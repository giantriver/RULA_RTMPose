# RULA_RTMPose

RULA_RTMPose is a desktop application for ergonomic risk assessment using computer vision.  
It detects human body keypoints with RTMPose and computes **RULA (Rapid Upper Limb Assessment)** scores in real time.  
The tool helps users quickly identify posture risk levels from a webcam, Kinect source, or uploaded video.

## What It Does

- Real-time posture analysis with live RULA scoring
- Offline analysis for uploaded videos
- Multiple input modes: webcam, Kinect, and RTM 3D workflow
- Visual result windows with history recording for review

## Tech Stack

- Python 3.11+
- PyQt6 (desktop UI)
- RTMLib + ONNX Runtime (pose estimation)
- OpenCV, NumPy, MediaPipe, Matplotlib

## Quick Start

```bash
pip install -e .
rula
```

Run directly in real-time mode:

```bash
rula --realtime
```

Optional arguments:

- `--camera-mode WEBCAM|KINECT|KINECT_RGB|RTMW3D`
- `--display-mode RULA|COORDINATES`

## Why This Project

This project demonstrates practical skills in computer vision integration, ergonomic analytics, and desktop application engineering for real-world workplace safety scenarios.
