# architecture를 보고 육각형 지표 중 power 지표를 구현하세요.
# 다른 부분은 절대 건들지 않는다. 오직 __init__.py에서만 해결
"""Power metric: 레퍼런스 대비 관절 속도 커버리지로 폭발력 채점."""

from typing import Any, Dict, List, Optional

import numpy as np

# 파워 측정 핵심 관절 (말단 관절 중심)
_POWER_JOINTS = [
    "left_wrist", "right_wrist",
    "left_elbow", "right_elbow",
    "left_ankle", "right_ankle",
    "left_knee", "right_knee",
    "left_hip", "right_hip",
]

# 말단 관절일수록 큰 가중치 (손목·발목이 폭발력 표현에 핵심)
_JOINT_WEIGHT: Dict[str, float] = {
    "left_wrist": 1.5, "right_wrist": 1.5,
    "left_elbow": 1.0, "right_elbow": 1.0,
    "left_ankle": 1.5, "right_ankle": 1.5,
    "left_knee": 1.0, "right_knee": 1.0,
    "left_hip": 0.8,  "right_hip": 0.8,
}


def _extract_positions(frames: List[Dict[str, Any]], joint: str) -> np.ndarray:
    """프레임 시퀀스에서 관절 (x, y, z) 배열 반환. shape: (n_frames, 3)"""
    pos = []
    for frame in frames:
        lm = frame.get("normalized_landmarks", {}).get(joint)
        if lm is None:
            pos.append([np.nan, np.nan, np.nan])
        else:
            pos.append([float(lm["x"]), float(lm["y"]), float(lm["z"])])
    return np.array(pos)


def _compute_joint_stats(frames: List[Dict[str, Any]], fps: float) -> Dict[str, Dict[str, float]]:
    """관절별 속도·가속도 통계 계산."""
    stats: Dict[str, Dict[str, float]] = {}
    for joint in _POWER_JOINTS:
        pos = _extract_positions(frames, joint)
        vel = np.linalg.norm(np.diff(pos, axis=0), axis=1) * fps
        vel = vel[~np.isnan(vel)]
        if len(vel) == 0:
            continue
        acc = np.abs(np.diff(vel)) if len(vel) >= 2 else np.array([0.0])
        stats[joint] = {
            "mean_velocity":     round(float(np.mean(vel)), 4),
            "p75_velocity":      round(float(np.percentile(vel, 75)), 4),
            "p95_velocity":      round(float(np.percentile(vel, 95)), 4),
            "mean_acceleration": round(float(np.mean(acc)), 4),
            "p75_acceleration":  round(float(np.percentile(acc, 75)), 4),
            "p95_acceleration":  round(float(np.percentile(acc, 95)), 4),
        }
    return stats


def score_power(
    user_extraction: Dict[str, Any],
    ref_extraction: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    파워 점수 계산 — ROM 방식과 동일한 커버리지 기반.

    ref_extraction 필수. 관절별 min(user_vel / ref_vel, 1.0) × 100 의 가중 평균.
    레퍼런스 이상으로 빠르면 100점, 느릴수록 비례 감점.
    같은 영상이면 100점.
    """
    user_frames: List[Dict[str, Any]] = user_extraction.get("frames", [])
    user_fps: float = float(user_extraction.get("fps", 30.0))

    if len(user_frames) < 2:
        return {
            "score": 0.0,
            "breakdown": {"error": "insufficient_frames", "total_frames": len(user_frames)},
            "frame_diffs": [],
        }

    if ref_extraction is None:
        return {
            "score": 0.0,
            "breakdown": {"error": "ref_extraction_required"},
            "frame_diffs": [],
        }

    ref_frames: List[Dict[str, Any]] = ref_extraction.get("frames", [])
    ref_fps: float = float(ref_extraction.get("fps", 30.0))

    if len(ref_frames) < 2:
        return {
            "score": 0.0,
            "breakdown": {"error": "ref_insufficient_frames"},
            "frame_diffs": [],
        }

    user_stats = _compute_joint_stats(user_frames, user_fps)
    ref_stats = _compute_joint_stats(ref_frames, ref_fps)

    weighted_coverage = 0.0
    total_w = 0.0
    joint_details: Dict[str, Any] = {}

    for joint in _POWER_JOINTS:
        u_vel = user_stats.get(joint, {}).get("mean_velocity", 0.0)
        r_vel = ref_stats.get(joint, {}).get("mean_velocity", 0.0)
        w = _JOINT_WEIGHT.get(joint, 1.0)

        # 레퍼런스가 정지 관절이면 사용자도 정지 → 만점
        coverage = 100.0 if r_vel < 1e-6 else min(u_vel / r_vel, 1.0) * 100.0

        joint_details[joint] = {
            "user_velocity": round(u_vel, 4),
            "ref_velocity":  round(r_vel, 4),
            "coverage_pct":  round(coverage, 2),
        }
        weighted_coverage += coverage * w
        total_w += w

    if total_w == 0.0:
        return {
            "score": 0.0,
            "breakdown": {"error": "no_landmark_data"},
            "frame_diffs": [],
        }

    final_score = round(weighted_coverage / total_w, 2)

    return {
        "score": final_score,
        "breakdown": {
            "user_fps": user_fps,
            "ref_fps": ref_fps,
            "user_total_frames": len(user_frames),
            "ref_total_frames": len(ref_frames),
            "joint_details": joint_details,
        },
        "frame_diffs": [],
    }
