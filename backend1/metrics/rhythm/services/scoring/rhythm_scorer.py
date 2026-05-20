"""Rhythm scorer: 사용자 동작의 리듬 규칙성 채점."""

from typing import Any, Dict, List

import numpy as np
from scipy.signal import find_peaks

_RHYTHM_KEYPOINTS = ["left_wrist", "right_wrist", "left_ankle", "right_ankle"]
_MIN_PEAK_DISTANCE = 5
_PROMINENCE_FACTOR = 0.3
_CV_SCALE = 2.0


def score_rhythm_from_extraction(user_extraction: Dict[str, Any]) -> Dict[str, Any]:
    """
    추출 데이터에서 리듬 점수 계산.
    반환: {"score": float, "breakdown": dict, "frame_diffs": list}
    """
    fps: float = float(user_extraction.get("fps") or 30.0)
    frames: List[Dict[str, Any]] = user_extraction.get("frames") or []

    if not frames:
        return {"score": 0.0, "breakdown": {"error": "no_frames"}, "frame_diffs": []}

    signal = _velocity_signal(frames, _RHYTHM_KEYPOINTS)
    stats = _detect_peaks(signal, fps)

    peak_count = len(stats["peak_indices"])
    cv = stats["cv"]

    consistency_score = round(float(np.clip(100.0 * (1.0 - cv * _CV_SCALE), 0.0, 100.0)), 2)

    if peak_count < 4:
        reliability_penalty = (4 - peak_count) * 10.0
        consistency_score = max(0.0, consistency_score - reliability_penalty)

    tempo_bpm = round(60.0 / stats["mean_sec"], 2) if stats["mean_sec"] > 0 else 0.0

    breakdown = {
        "tempo_bpm_estimate": tempo_bpm,
        "peak_count": peak_count,
        "beat_interval_mean_sec": stats["mean_sec"],
        "beat_interval_std_sec": stats["std_sec"],
        "beat_interval_cv": cv,
        "rhythm_consistency": consistency_score,
        "keypoints_used": _RHYTHM_KEYPOINTS,
    }

    return {"score": consistency_score, "breakdown": breakdown, "frame_diffs": []}


def _velocity_signal(frames: List[Dict[str, Any]], keypoints: List[str]) -> np.ndarray:
    positions: List[np.ndarray] = []
    for frame in frames:
        lm = frame.get("normalized_landmarks") or {}
        coords: List[float] = []
        for kp in keypoints:
            pt = lm.get(kp)
            if pt:
                coords.extend([pt["x"], pt["y"]])
        positions.append(
            np.array(coords, dtype=float) if coords else np.zeros(len(keypoints) * 2)
        )

    if len(positions) < 2:
        return np.zeros(max(len(positions), 1))

    pos_arr = np.array(positions)
    diffs = np.linalg.norm(np.diff(pos_arr, axis=0), axis=1)
    return np.concatenate([[0.0], diffs])


def _detect_peaks(signal: np.ndarray, fps: float) -> Dict[str, Any]:
    if signal.std() < 1e-9:
        return {"peak_indices": [], "intervals_sec": [], "mean_sec": 0.0, "std_sec": 0.0, "cv": 1.0}

    prominence = max(signal.std() * _PROMINENCE_FACTOR, 1e-6)
    peaks, _ = find_peaks(signal, distance=_MIN_PEAK_DISTANCE, prominence=prominence)

    if len(peaks) < 2:
        return {
            "peak_indices": peaks.tolist(),
            "intervals_sec": [],
            "mean_sec": 0.0,
            "std_sec": 0.0,
            "cv": 1.0,
        }

    intervals_sec = np.diff(peaks).astype(float) / fps
    mean_sec = float(intervals_sec.mean())
    std_sec = float(intervals_sec.std())
    cv = std_sec / mean_sec if mean_sec > 1e-9 else 1.0

    return {
        "peak_indices": peaks.tolist(),
        "intervals_sec": [round(v, 4) for v in intervals_sec.tolist()],
        "mean_sec": round(mean_sec, 4),
        "std_sec": round(std_sec, 4),
        "cv": round(cv, 4),
    }
