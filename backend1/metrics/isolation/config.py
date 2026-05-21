"""Isolation metric — 로컬 경로·YOLO 설정."""

from pathlib import Path

ISOLATION_ROOT = Path(__file__).resolve().parent
DATA_RAW = ISOLATION_ROOT / "data" / "raw"
DATA_ARTIFACTS = ISOLATION_ROOT / "data" / "artifacts"

# 기준 Shorts (팀 고정)
REF_VIDEO_URL = "https://www.youtube.com/shorts/YzTywjy0VXU"
REF_VIDEO_NAME = "ref.mp4"

# YOLO11 (ultralytics) — n=빠름, s/m=정확도↑
YOLO_MODEL = "yolo11n.pt"
YOLO_CONF = 0.4
YOLO_IOU = 0.5
YOLO_PERSON_CLASS = 0
CROP_PADDING_RATIO = 0.15

# MediaPipe solutions.pose — model_complexity 2 = Heavy
MP_MODEL_COMPLEXITY = 2
MP_MIN_DETECTION_CONFIDENCE = 0.5
MP_MIN_TRACKING_CONFIDENCE = 0.5
MP_SMOOTH_WINDOW = 3
