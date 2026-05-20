"""Rhythm 전용 MediaPipe 추출기 — 손목·발목 랜드마크만 추출."""

from typing import Any, Dict, List

import cv2
import mediapipe as mp
import numpy as np

_POSE = mp.solutions.pose

_KEYPOINT_IDX = {
    "left_wrist":     15,
    "right_wrist":    16,
    "left_ankle":     27,
    "right_ankle":    28,
    "left_hip":       23,
    "right_hip":      24,
    "left_shoulder":  11,
    "right_shoulder": 12,
}


def extract_rhythm_data(video_path: str) -> Dict[str, Any]:
    """
    영상에서 리듬 채점에 필요한 최소 데이터만 추출.

    반환:
        {
          "fps": float,
          "total_frames": int,
          "frames": [
            {
              "frame_index": int,
              "time_sec": float,
              "normalized_landmarks": {
                "left_wrist": {"x":…,"y":…,"z":…}, …
              }
            }, …
          ]
        }
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")

    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0

    pose = _POSE.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    raw: List[Dict[str, Any] | None] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = pose.process(rgb)
        if result.pose_landmarks:
            lm = result.pose_landmarks.landmark
            raw.append({
                name: {"x": lm[idx].x, "y": lm[idx].y, "z": lm[idx].z}
                for name, idx in _KEYPOINT_IDX.items()
            })
        else:
            raw.append(None)

    cap.release()
    pose.close()

    filled = _fill_missing(raw)
    frames_output: List[Dict[str, Any]] = []

    for fi, pts in enumerate(filled):
        norm = _normalize(pts)
        frames_output.append({
            "frame_index": fi,
            "time_sec": round(fi / fps, 4),
            "normalized_landmarks": norm,
        })

    return {"fps": fps, "total_frames": len(frames_output), "frames": frames_output}


def _fill_missing(raw: List) -> List[Dict]:
    """None(미검출) 프레임을 앞뒤 보간으로 채운다."""
    n = len(raw)
    if n == 0:
        return []

    first_valid = next((r for r in raw if r is not None), None)
    if first_valid is None:
        zero = {name: {"x": 0.0, "y": 0.0, "z": 0.0} for name in _KEYPOINT_IDX}
        return [zero] * n

    filled = [first_valid if r is None else r for r in raw]

    for name in _KEYPOINT_IDX:
        for coord in ("x", "y", "z"):
            vals = [filled[i][name][coord] for i in range(n)]
            vals = _interpolate(vals)
            for i in range(n):
                filled[i][name][coord] = vals[i]

    return filled


def _interpolate(vals: List[float]) -> List[float]:
    arr = np.array(vals, dtype=float)
    nans = np.isnan(arr)
    if not nans.any():
        return vals
    idx = np.arange(len(arr))
    arr[nans] = np.interp(idx[nans], idx[~nans], arr[~nans])
    return arr.tolist()


def _normalize(pts: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """Mid-Hip 원점 이동 + Torso Length 스케일 제거."""
    mid_hip = {
        "x": (pts["left_hip"]["x"] + pts["right_hip"]["x"]) / 2,
        "y": (pts["left_hip"]["y"] + pts["right_hip"]["y"]) / 2,
        "z": (pts["left_hip"]["z"] + pts["right_hip"]["z"]) / 2,
    }
    mid_shoulder = {
        "x": (pts["left_shoulder"]["x"] + pts["right_shoulder"]["x"]) / 2,
        "y": (pts["left_shoulder"]["y"] + pts["right_shoulder"]["y"]) / 2,
        "z": (pts["left_shoulder"]["z"] + pts["right_shoulder"]["z"]) / 2,
    }
    torso = float(np.sqrt(
        (mid_shoulder["x"] - mid_hip["x"]) ** 2 +
        (mid_shoulder["y"] - mid_hip["y"]) ** 2 +
        (mid_shoulder["z"] - mid_hip["z"]) ** 2
    ))
    if torso < 1e-6:
        torso = 1.0

    result: Dict[str, Dict[str, float]] = {}
    for name in ("left_wrist", "right_wrist", "left_ankle", "right_ankle"):
        result[name] = {
            "x": (pts[name]["x"] - mid_hip["x"]) / torso,
            "y": (pts[name]["y"] - mid_hip["y"]) / torso,
            "z": (pts[name]["z"] - mid_hip["z"]) / torso,
        }
    return result
