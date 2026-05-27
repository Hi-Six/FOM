"""
동작 양상 전환 기반 구간 분할 — 가동 관절 집합(Jaccard) 변화로 경계 검출.
멈춤이 없어도 손↔발 등 주도 관절이 바뀌면 경계를 둔다.
"""

from __future__ import annotations

from typing import Any

import numpy as np

_ACTIVATION_JOINTS = (
    "left_wrist",
    "right_wrist",
    "left_elbow",
    "right_elbow",
    "left_ankle",
    "right_ankle",
    "left_knee",
    "right_knee",
    "left_shoulder",
    "right_shoulder",
)

_DEFAULT_MIN_SEGMENT_SEC = 0.3
_DEFAULT_MIN_BOUNDARY_GAP_SEC = 0.4
_DEFAULT_PROFILE_DELTA = 0.35
_DEFAULT_MIN_RUN_FRAMES = 3
_DEFAULT_MAX_SEGMENTS = 12
_VISIBILITY_MIN = 0.5


def _per_joint_velocities(
    frames: list[dict[str, Any]],
    joint_names: tuple[str, ...],
    visibility_threshold: float,
) -> tuple[np.ndarray, list[float]]:
    """shape (n_frames, n_joints), times."""
    n_j = len(joint_names)
    n = len(frames)
    times = [float(f.get("time_sec", 0.0)) for f in frames]
    pos = np.full((n, n_j, 2), np.nan, dtype=float)

    for i, frame in enumerate(frames):
        lm = frame.get("normalized_landmarks") or {}
        for j, name in enumerate(joint_names):
            pt = lm.get(name)
            if not pt:
                continue
            vis = float(pt.get("visibility", 1.0))
            if vis < visibility_threshold:
                continue
            pos[i, j, 0] = float(pt["x"])
            pos[i, j, 1] = float(pt["y"])

    vel = np.zeros((n, n_j), dtype=float)
    for i in range(1, n):
        for j in range(n_j):
            if np.isnan(pos[i, j, 0]) or np.isnan(pos[i - 1, j, 0]):
                continue
            d = pos[i, j] - pos[i - 1, j]
            vel[i, j] = float(np.linalg.norm(d))
    return vel, times


def _auto_activation_threshold(vel: np.ndarray) -> float:
    nz = vel[vel > 1e-9]
    if len(nz) == 0:
        return 0.008
    p35 = float(np.percentile(nz, 35))
    return float(max(0.004, min(0.02, p35)))


def _active_set(
    vel_row: np.ndarray,
    joint_names: tuple[str, ...],
    tau: float,
) -> set[str]:
    out: set[str] = set()
    for j, name in enumerate(joint_names):
        if float(vel_row[j]) >= tau:
            out.add(name)
    return out


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return 1.0 - inter / union


def _merge_boundaries(times: list[float], min_gap_sec: float) -> list[float]:
    merged: list[float] = []
    for t in sorted(times):
        if merged and t - merged[-1] < min_gap_sec:
            continue
        merged.append(round(t, 4))
    return merged


def _segments_from_bounds(
    bounds: list[float],
    min_segment_sec: float,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for i in range(len(bounds) - 1):
        t0, t1 = float(bounds[i]), float(bounds[i + 1])
        if t1 - t0 < min_segment_sec:
            continue
        segments.append(
            {
                "index": len(segments),
                "start_sec": round(t0, 4),
                "end_sec": round(t1, 4),
                "duration_sec": round(t1 - t0, 4),
            }
        )
    return segments


def _cap_segments(
    boundaries: list[float],
    profile_dist: list[float],
    times: list[float],
    window_start: float,
    window_end: float,
    min_segment_sec: float,
    max_segments: int,
) -> tuple[list[float], list[dict[str, Any]]]:
    """구간 수 상한 — 경계별 평균 profile distance 큰 순으로 유지."""
    bounds = [window_start] + boundaries + [window_end]
    segs = _segments_from_bounds(bounds, min_segment_sec)
    if len(segs) <= max_segments:
        return boundaries, segs

    # 경계 시각 → 인덱스
    t_to_idx = {round(t, 4): i for i, t in enumerate(times)}
    scores: list[tuple[float, float]] = []
    for b in boundaries:
        idx = min(range(len(times)), key=lambda i: abs(times[i] - b))
        lo = max(0, idx - 1)
        hi = min(len(profile_dist) - 1, idx + 1)
        sc = float(np.mean(profile_dist[lo : hi + 1])) if profile_dist else 0.0
        scores.append((sc, b))
    scores.sort(reverse=True)
    keep = sorted([b for _, b in scores[: max_segments - 1]], key=lambda x: x)
    return keep, _segments_from_bounds(
        [window_start] + keep + [window_end], min_segment_sec
    )


def detect_activation_boundaries_and_segments(
    frames: list[dict[str, Any]],
    *,
    window_start_sec: float,
    window_end_sec: float,
    visibility_threshold: float = _VISIBILITY_MIN,
    profile_delta: float = _DEFAULT_PROFILE_DELTA,
    min_run_frames: int = _DEFAULT_MIN_RUN_FRAMES,
    min_segment_sec: float = _DEFAULT_MIN_SEGMENT_SEC,
    min_boundary_gap_sec: float = _DEFAULT_MIN_BOUNDARY_GAP_SEC,
    max_segments: int = _DEFAULT_MAX_SEGMENTS,
) -> dict[str, Any]:
    """
    Returns pause_detect 호환 키:
      pause_instants_sec (= boundary 시각),
      motion_segments, boundary_instants_sec, segmentation_mode.
    """
    pool = [
        f
        for f in frames
        if window_start_sec <= float(f.get("time_sec", 0.0)) <= window_end_sec
    ]
    if len(pool) < 4:
        return {
            "pause_instants_sec": [],
            "boundary_instants_sec": [],
            "motion_segments": [],
            "segmentation_mode": "activation",
            "error": "too_few_frames",
        }

    vel, times = _per_joint_velocities(
        pool, _ACTIVATION_JOINTS, visibility_threshold
    )
    tau = _auto_activation_threshold(vel)
    n = len(pool)
    active_sets: list[set[str]] = [
        _active_set(vel[i], _ACTIVATION_JOINTS, tau) for i in range(n)
    ]
    profile_dist = [0.0]
    for i in range(1, n):
        profile_dist.append(_jaccard_distance(active_sets[i], active_sets[i - 1]))

    raw_boundaries: list[float] = []
    run = 0
    run_start_idx: int | None = None
    for i in range(1, n):
        if profile_dist[i] > profile_delta:
            if run == 0:
                run_start_idx = i
            run += 1
            if run >= min_run_frames and run_start_idx is not None:
                raw_boundaries.append(round(times[run_start_idx], 4))
                run = 0
                run_start_idx = None
        else:
            run = 0
            run_start_idx = None

    boundaries = _merge_boundaries(raw_boundaries, min_boundary_gap_sec)
    boundaries, segments = _cap_segments(
        boundaries,
        profile_dist,
        times,
        window_start_sec,
        window_end_sec,
        min_segment_sec,
        max_segments,
    )

    if not segments:
        segments = [
            {
                "index": 0,
                "start_sec": round(window_start_sec, 4),
                "end_sec": round(window_end_sec, 4),
                "duration_sec": round(window_end_sec - window_start_sec, 4),
            }
        ]

    return {
        "pause_instants_sec": boundaries,
        "boundary_instants_sec": boundaries,
        "motion_segments": segments,
        "segmentation_mode": "activation",
        "activation_threshold": round(tau, 6),
        "profile_delta": profile_delta,
        "min_run_frames": min_run_frames,
        "frame_count": len(pool),
        "boundary_count": len(boundaries),
        "motion_segment_count": len(segments),
        "pause_count": len(boundaries),
    }
