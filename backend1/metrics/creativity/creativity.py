"""
창의성(creativity) metric — ARCHITECTURE.md §4·§5 준수.

입력: `aligned_pairs` (읽기 전용, 오케스트레이터가 정렬 후 전달)
출력: `{"score": float, "breakdown": dict, "frame_diffs": list}` — score 는 0~100, 동기 함수.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

# --- 휴리스틱 가중·스케일 (오케스트레이터와 무관, 본 모듈 내부 상수) ---
_W_MEAN_DIV = 0.35
_W_STD_DIV = 0.25
_W_MOTION = 0.40
_K_MEAN = 8.0
_K_STD = 15.0
_K_MOTION = 10.0


def _flatten_numbers(obj: Any, out: list[float]) -> None:
    if obj is None or isinstance(obj, (str, bytes, bytearray)):
        return
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            out.append(float(obj))
        return
    if isinstance(obj, Sequence):
        for x in obj:
            _flatten_numbers(x, out)
        return
    if isinstance(obj, Mapping):
        for k in sorted(obj.keys(), key=lambda x: str(x)):
            _flatten_numbers(obj[k], out)


def _pose_vector(pose: Mapping[str, Any]) -> list[float]:
    """normalized_landmarks → joint_angles → bone_vectors 순으로 첫 유효 벡터."""
    for key in ("normalized_landmarks", "joint_angles", "bone_vectors"):
        block = pose.get(key)
        if not block:
            continue
        vals: list[float] = []
        _flatten_numbers(block, vals)
        if vals:
            return vals
    return []


def _l2_mean_sq_diff(a: Sequence[float], b: Sequence[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    s = 0.0
    for i in range(n):
        d = a[i] - b[i]
        s += d * d
    return math.sqrt(s / n)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pstdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_creativity(aligned_pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """
    동기 채점 함수. ARCHITECTURE.md — creativity 는 `aligned_pairs` 만 입력으로 받는다.

    Parameters
    ----------
    aligned_pairs :
        각 원소는 user_frame, ref_frame, user, ref 키를 가진 매핑.

    Returns
    -------
    dict
        {"score": 0~100, "breakdown": {...}, "frame_diffs": [...]}

    Notes
    -----
    - 창의성 휴리스틱: 정렬 프레임마다 user/ref 구조적 거리(이탈) 평균·분산,
      및 user 연속 프레임 움직임 강도를 조합한다.
    - 포즈 데이터가 없으면 score 0 에 가깝게 두어 오케스트레이터가 무의미한 고득점을
      내지 않도록 한다 (데이터 검증은 상위에서도 수행 가정).
    """
    pairs = list(aligned_pairs)
    if not pairs:
        return {
            "score": 0.0,
            "breakdown": {"reason": "empty_aligned_pairs"},
            "frame_diffs": [],
        }

    divergences: list[float] = []
    frame_diffs: list[dict[str, Any]] = []
    prev_user_vec: list[float] | None = None
    motions: list[float] = []

    for pair in pairs:
        user = pair.get("user") or {}
        ref = pair.get("ref") or {}
        uf = pair.get("user_frame")
        rf = pair.get("ref_frame")
        u = _pose_vector(user)
        r = _pose_vector(ref)

        if u and r:
            d = _l2_mean_sq_diff(u, r)
            divergences.append(d)
            frame_diffs.append(
                {
                    "user_frame": uf,
                    "ref_frame": rf,
                    "divergence": round(d, 6),
                }
            )
        else:
            frame_diffs.append(
                {
                    "user_frame": uf,
                    "ref_frame": rf,
                    "divergence": None,
                    "skipped": True,
                }
            )

        if u:
            if prev_user_vec is not None and prev_user_vec and u:
                motions.append(_l2_mean_sq_diff(u, prev_user_vec))
            prev_user_vec = u

    if not divergences:
        return {
            "score": 0.0,
            "breakdown": {
                "reason": "no_comparable_pose_vectors",
                "pairs_evaluated": len(pairs),
            },
            "frame_diffs": frame_diffs,
        }

    mean_div = _mean(divergences)
    std_div = _pstdev(divergences)
    motion_intensity = _mean(motions) if motions else 0.0

    t_m = math.tanh(mean_div * _K_MEAN)
    t_s = math.tanh(std_div * _K_STD)
    t_o = math.tanh(motion_intensity * _K_MOTION)

    static_factor = 1.0 if motion_intensity >= 1e-9 else 0.5

    w_sum = _W_MEAN_DIV + _W_STD_DIV + _W_MOTION
    combined = (
        _W_MEAN_DIV * t_m + _W_STD_DIV * t_s + _W_MOTION * t_o
    ) * static_factor / w_sum
    score = 100.0 * _clamp(combined, 0.0, 1.0)

    return {
        "score": round(score, 2),
        "breakdown": {
            "mean_divergence": round(mean_div, 6),
            "divergence_std": round(std_div, 6),
            "motion_intensity": round(motion_intensity, 6),
            "pairs_evaluated": len(pairs),
            "pairs_used": len(divergences),
            "motion_segments": len(motions),
            "weights": {
                "mean_divergence": _W_MEAN_DIV,
                "divergence_std": _W_STD_DIV,
                "motion": _W_MOTION,
            },
        },
        "frame_diffs": frame_diffs,
    }
