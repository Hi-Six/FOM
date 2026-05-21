"""YOLO bbox crop 위에서 MediaPipe Pose (solutions API, Heavy) 추출."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np

from metrics.isolation.config import (
    CROP_PADDING_RATIO,
    MP_MIN_DETECTION_CONFIDENCE,
    MP_MIN_TRACKING_CONFIDENCE,
    MP_MODEL_COMPLEXITY,
)
from metrics.isolation.pipeline.tracker import TrackFrame, _clip_bbox_with_padding

LANDMARK_NAMES: Tuple[str, ...] = (
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
)


def _check_solutions_api() -> None:
    if not hasattr(mp, "solutions"):
        raise ImportError(
            "mediapipe.solutions 가 없습니다. "
            "aiproject에서: pip install \"mediapipe>=0.10.14,<0.10.31\" "
            "(0.10.31 이상은 legacy API 제거됨. [solutions] extra 는 PyPI에 없음)"
        )


def map_crop_landmarks_to_full_frame(
    crop_landmarks: Dict[str, dict],
    bbox_xyxy: Tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
) -> Dict[str, dict]:
    x1, y1, x2, y2 = bbox_xyxy
    cw = max(1, x2 - x1)
    ch = max(1, y2 - y1)
    out: Dict[str, dict] = {}
    for name in LANDMARK_NAMES:
        lm = crop_landmarks[name]
        out[name] = {
            "x": float((x1 + lm["x"] * cw) / frame_width),
            "y": float((y1 + lm["y"] * ch) / frame_height),
            "z": float(lm["z"]),
            "visibility": float(lm.get("visibility", 1.0)),
        }
    return out


class CropPoseExtractor:
    """mp.solutions.pose.Pose — model_complexity=2 (Heavy), crop ROI."""

    def __init__(
        self,
        model_complexity: int = MP_MODEL_COMPLEXITY,
        min_detection_confidence: float = MP_MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = MP_MIN_TRACKING_CONFIDENCE,
    ) -> None:
        _check_solutions_api()
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            smooth_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def close(self) -> None:
        self._pose.close()

    def __enter__(self) -> "CropPoseExtractor":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def process_crop(self, bgr_crop: np.ndarray) -> Optional[Dict[str, dict]]:
        if bgr_crop.size == 0 or bgr_crop.shape[0] < 32 or bgr_crop.shape[1] < 32:
            return None
        rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return None
        landmarks: Dict[str, dict] = {}
        for name, lm in zip(LANDMARK_NAMES, result.pose_landmarks.landmark):
            landmarks[name] = {
                "x": float(lm.x),
                "y": float(lm.y),
                "z": float(lm.z),
                "visibility": float(lm.visibility),
            }
        return landmarks

    def process_frame_with_bbox(
        self,
        bgr_frame: np.ndarray,
        bbox_xyxy: Tuple[int, int, int, int],
        padding_ratio: float = CROP_PADDING_RATIO,
    ) -> Optional[Dict[str, dict]]:
        h, w = bgr_frame.shape[:2]
        box = _clip_bbox_with_padding(bbox_xyxy, w, h, padding_ratio)
        x1, y1, x2, y2 = box
        crop = bgr_frame[y1:y2, x1:x2]
        crop_lms = self.process_crop(crop)
        if crop_lms is None:
            return None
        return map_crop_landmarks_to_full_frame(crop_lms, box, w, h)


def raw_row_from_landmarks(landmarks: Dict[str, dict]) -> List[float]:
    row: List[float] = []
    for name in LANDMARK_NAMES:
        lm = landmarks[name]
        row.extend([lm["x"], lm["y"], lm["z"], lm["visibility"]])
    return row


def nan_row() -> List[float]:
    return [np.nan] * (len(LANDMARK_NAMES) * 4)


def track_frame_to_bbox(track: TrackFrame) -> Tuple[int, int, int, int]:
    if CROP_PADDING_RATIO > 0:
        return _clip_bbox_with_padding(
            track.bbox_xyxy,
            track.frame_width,
            track.frame_height,
            CROP_PADDING_RATIO,
        )
    return track.bbox_xyxy
