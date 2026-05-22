"""Isolation metric — 로컬 경로·YOLO 설정."""

from pathlib import Path

ISOLATION_ROOT = Path(__file__).resolve().parent
DATA_RAW = ISOLATION_ROOT / "data" / "raw"
DATA_ARTIFACTS = ISOLATION_ROOT / "data" / "artifacts"
DATA_MODELS = ISOLATION_ROOT / "data" / "models"

# 기준 Shorts (팀 고정)
REF_VIDEO_URL = "https://www.youtube.com/shorts/YzTywjy0VXU"
REF_VIDEO_NAME = "ref.mp4"

# YOLO11 (ultralytics) — n=빠름, s/m=정확도↑ (없으면 ultralytics가 자동 다운로드)
YOLO_MODEL = str(DATA_MODELS / "yolo11n.pt")
YOLO_CONF = 0.4
YOLO_IOU = 0.5
YOLO_PERSON_CLASS = 0
CROP_PADDING_RATIO = 0.15

# MediaPipe Tasks API — Pose Landmarker Heavy (.task, Git 제외)
MP_POSE_MODEL = str(DATA_MODELS / "pose_landmarker_heavy.task")
MP_MIN_DETECTION_CONFIDENCE = 0.5
MP_MIN_TRACKING_CONFIDENCE = 0.5
MP_SMOOTH_WINDOW = 3
