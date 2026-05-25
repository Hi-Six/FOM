"""
Isolation 채점 — region 그룹 × 동작 윈도우 기반.

ref/user 각각의 아이솔레이션 비율(isolation_ratio)을 윈도우 단위로 추출하여
구간·부위·비율 3축으로 비교한다.

beat 정렬 시: 같은 beat_index 내 ref_frame이 모두 동일하므로
  비트 내부가 아닌 연속 비트 대표 프레임 간 전환으로 모션을 계산한다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from metrics.isolation.align import align_and_save, align_from_paths
from metrics.isolation.pipeline.geometry import BONE_SEGMENTS
from metrics.isolation.pipeline.io import load_extraction_json, save_json

ALL_BONES: Tuple[str, ...] = tuple(name for name, _, _ in BONE_SEGMENTS)

REGION_BONES: Dict[str, Tuple[str, ...]] = {
    "torso": ("torso",),
    "arms": (
        "left_upper_arm",
        "left_forearm",
        "right_upper_arm",
        "right_forearm",
    ),
    "legs": (
        "left_thigh",
        "left_shin",
        "right_thigh",
        "right_shin",
        "left_foot",
        "right_foot",
    ),
}

_MOTION_EPS = 0.015
# ref isolation_ratio 이상이어야 아이솔레이션 구간으로 인정
_ISOLATION_SEGMENT_THRESHOLD = 0.40
# 잘못된 부위를 아이솔레이션할 때 점수 배율
_REGION_MISMATCH_FACTOR = 0.30
# beat_index 없을 때 고정 윈도우 크기·슬라이드 스텝
_FIXED_WINDOW_SIZE = 5
_FIXED_WINDOW_STEP = 3


# ── 기본 bone 유틸 (내부·하위 호환) ─────────────────────────────────

def _bone_unit(bone: Dict[str, float]) -> np.ndarray:
    return np.array(
        [float(bone.get("x", 0)), float(bone.get("y", 0)), float(bone.get("z", 0))],
        dtype=np.float64,
    )


def _bone_motion(
    frame_a: Dict[str, Any],
    frame_b: Dict[str, Any],
    bone: str,
) -> float:
    """연속 프레임 bone 방향 변화량 (0~2 스케일)."""
    bv_a = (frame_a.get("bone_vectors") or {}).get(bone)
    bv_b = (frame_b.get("bone_vectors") or {}).get(bone)
    if not bv_a or not bv_b:
        return 0.0
    u0 = _bone_unit(bv_a)
    u1 = _bone_unit(bv_b)
    n0 = float(np.linalg.norm(u0))
    n1 = float(np.linalg.norm(u1))
    if n0 < 1e-8 or n1 < 1e-8:
        return 0.0
    u0 /= n0
    u1 /= n1
    cos_sim = float(np.clip(np.dot(u0, u1), -1.0, 1.0))
    angle_term = 1.0 - cos_sim
    mag_a = float(bv_a.get("magnitude", 0.0))
    mag_b = float(bv_b.get("magnitude", 0.0))
    mag_term = abs(mag_b - mag_a) / max(mag_a, mag_b, 1e-6)
    return angle_term + 0.5 * mag_term


# ── region motion 계산 ───────────────────────────────────────────────

def _region_motions_between(
    frame_a: Dict[str, Any],
    frame_b: Dict[str, Any],
) -> Dict[str, float]:
    """두 프레임 간 region별 motion 합산."""
    return {
        region: sum(_bone_motion(frame_a, frame_b, b) for b in bones)
        for region, bones in REGION_BONES.items()
    }


def _region_motions_for_window(
    pairs: List[Dict[str, Any]],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    고정 윈도우용: 윈도우 내 연속 pair 전환의 region별 평균 motion.
    반환: (ref_region_motions, user_region_motions)
    """
    ref_acc: Dict[str, List[float]] = {r: [] for r in REGION_BONES}
    user_acc: Dict[str, List[float]] = {r: [] for r in REGION_BONES}

    for i in range(1, len(pairs)):
        prev, curr = pairs[i - 1], pairs[i]
        for region, bones in REGION_BONES.items():
            ref_acc[region].append(
                sum(_bone_motion(prev["ref"], curr["ref"], b) for b in bones)
            )
            user_acc[region].append(
                sum(_bone_motion(prev["user"], curr["user"], b) for b in bones)
            )

    ref_avg = {r: float(np.mean(v)) if v else 0.0 for r, v in ref_acc.items()}
    user_avg = {r: float(np.mean(v)) if v else 0.0 for r, v in user_acc.items()}
    return ref_avg, user_avg


def _isolation_ratio(
    region_motions: Dict[str, float],
) -> Tuple[float, Optional[str]]:
    """
    isolation_ratio = dominant_region_motion / total_motion.
    total이 _MOTION_EPS 미만이면 (0.0, None).
    """
    total = sum(region_motions.values())
    if total < _MOTION_EPS:
        return 0.0, None
    dominant = max(region_motions, key=region_motions.get)
    return region_motions[dominant] / total, dominant


# ── 전환 채점 ────────────────────────────────────────────────────────

def _score_transition(
    ref_rm: Dict[str, float],
    user_rm: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """
    한 전환(비트 간 또는 윈도우)의 isolation 점수.

    ref isolation_ratio < _ISOLATION_SEGMENT_THRESHOLD → None (아이솔레이션 구간 아님).

    점수 구성
    - ratio_score  : ref/user isolation_ratio 유사도 (0~1)
    - region_factor: 같은 부위를 아이솔레이션했는지 (불일치 시 0.30 배율)
    - score        : 100 × ratio_score × region_factor
    """
    ref_ratio, ref_region = _isolation_ratio(ref_rm)
    user_ratio, user_region = _isolation_ratio(user_rm)

    if ref_ratio < _ISOLATION_SEGMENT_THRESHOLD or ref_region is None:
        return None

    region_match = (user_region == ref_region)
    region_factor = 1.0 if region_match else _REGION_MISMATCH_FACTOR

    ratio_score = max(
        0.0,
        1.0 - abs(user_ratio - ref_ratio) / max(ref_ratio, 0.1),
    )

    return {
        "score": round(100.0 * ratio_score * region_factor, 2),
        "ref_region": ref_region,
        "user_region": user_region,
        "ref_isolation_ratio": round(ref_ratio, 4),
        "user_isolation_ratio": round(user_ratio, 4),
        "region_match": region_match,
        "ratio_score": round(ratio_score, 4),
    }


# ── beat 전환 채점 ───────────────────────────────────────────────────

def _score_beat_transitions(
    sorted_pairs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Beat 정렬 전용.

    같은 beat_index 내 모든 pair가 동일 ref_frame을 가리키므로
    비트 내부 전환이 아닌 연속 비트 대표 프레임 간(beat k → beat k+1) 전환을 채점한다.
    """
    beat_groups: Dict[int, List[Dict[str, Any]]] = {}
    for p in sorted_pairs:
        bi = int(p.get("beat_index", 0))
        beat_groups.setdefault(bi, []).append(p)

    beat_indices = sorted(beat_groups.keys())
    if len(beat_indices) < 2:
        return []

    # 각 비트의 대표 pair: 비트 그룹 중간값 사용
    reps = {
        bi: beat_groups[bi][len(beat_groups[bi]) // 2]
        for bi in beat_indices
    }

    results: List[Dict[str, Any]] = []
    for i in range(1, len(beat_indices)):
        prev_bi = beat_indices[i - 1]
        curr_bi = beat_indices[i]
        prev_rep = reps[prev_bi]
        curr_rep = reps[curr_bi]

        ref_rm = _region_motions_between(prev_rep["ref"], curr_rep["ref"])
        user_rm = _region_motions_between(prev_rep["user"], curr_rep["user"])

        result = _score_transition(ref_rm, user_rm)
        if result is None:
            continue

        result["beat_index"] = curr_bi
        result["user_frame_start"] = int(prev_rep["user_frame"])
        result["user_frame_end"] = int(curr_rep["user_frame"])
        results.append(result)

    return results


# ── 동작 단위 채점 ──────────────────────────────────────────────────

def _score_motion_segments(
    sorted_pairs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    동작 단위 채점 (beat 정렬 전용).

    연속된 비트 전환 중 ref의 dominant region이 동일하고
    isolation_ratio >= threshold 인 구간을 하나의 '동작'으로 묶는다.
    각 동작 단위에서 ref/user region motion을 평균 → 노이즈 감소.

    비트 단위 채점(_score_beat_transitions)보다 실제 동작 경계에 맞고
    단일 비트 노이즈에 강하다.
    """
    beat_groups: Dict[int, List[Dict[str, Any]]] = {}
    for p in sorted_pairs:
        bi = int(p.get("beat_index", 0))
        beat_groups.setdefault(bi, []).append(p)

    beat_indices = sorted(beat_groups.keys())
    if len(beat_indices) < 2:
        return []

    reps = {
        bi: beat_groups[bi][len(beat_groups[bi]) // 2]
        for bi in beat_indices
    }

    # 연속 비트 쌍마다 region motion + isolation_ratio 계산
    transitions: List[Dict[str, Any]] = []
    for i in range(1, len(beat_indices)):
        prev_bi = beat_indices[i - 1]
        curr_bi = beat_indices[i]
        ref_rm = _region_motions_between(reps[prev_bi]["ref"], reps[curr_bi]["ref"])
        user_rm = _region_motions_between(reps[prev_bi]["user"], reps[curr_bi]["user"])
        ref_ratio, ref_region = _isolation_ratio(ref_rm)
        transitions.append(
            {
                "prev_bi": prev_bi,
                "curr_bi": curr_bi,
                "ref_rm": ref_rm,
                "user_rm": user_rm,
                "ref_ratio": ref_ratio,
                "ref_region": ref_region,
            }
        )

    # 같은 ref_region이 연속되는 구간 → 하나의 동작 단위로 묶어 채점
    results: List[Dict[str, Any]] = []
    i = 0
    while i < len(transitions):
        t = transitions[i]
        if t["ref_ratio"] < _ISOLATION_SEGMENT_THRESHOLD or t["ref_region"] is None:
            i += 1
            continue

        seg_region = t["ref_region"]
        j = i + 1
        while (
            j < len(transitions)
            and transitions[j]["ref_region"] == seg_region
            and transitions[j]["ref_ratio"] >= _ISOLATION_SEGMENT_THRESHOLD
        ):
            j += 1

        seg = transitions[i:j]

        # 동작 단위 내 region motion 평균 → 채점
        agg_ref = {
            r: float(np.mean([s["ref_rm"][r] for s in seg]))
            for r in REGION_BONES
        }
        agg_user = {
            r: float(np.mean([s["user_rm"][r] for s in seg]))
            for r in REGION_BONES
        }

        result = _score_transition(agg_ref, agg_user)
        if result is not None:
            result.update(
                {
                    "beat_start": seg[0]["prev_bi"],
                    "beat_end": seg[-1]["curr_bi"],
                    "beat_count": len(seg),
                    "user_frame_start": int(reps[seg[0]["prev_bi"]]["user_frame"]),
                    "user_frame_end": int(reps[seg[-1]["curr_bi"]]["user_frame"]),
                }
            )
            results.append(result)

        i = j

    return results


# ── 고정 윈도우 채점 ─────────────────────────────────────────────────

def _score_fixed_windows(
    sorted_pairs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """고정 윈도우 단위 채점 (beat_index 없는 time 정렬용)."""
    results: List[Dict[str, Any]] = []
    n = len(sorted_pairs)
    w_idx = 0
    i = 0
    while i + _FIXED_WINDOW_SIZE <= n:
        window = sorted_pairs[i : i + _FIXED_WINDOW_SIZE]
        ref_rm, user_rm = _region_motions_for_window(window)
        result = _score_transition(ref_rm, user_rm)
        if result is not None:
            result["beat_index"] = w_idx
            result["user_frame_start"] = int(window[0]["user_frame"])
            result["user_frame_end"] = int(window[-1]["user_frame"])
            results.append(result)
        i += _FIXED_WINDOW_STEP
        w_idx += 1
    return results


# ── 메인 채점 함수 ───────────────────────────────────────────────────

def score_isolation(aligned_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Region 그룹 × 동작 단위 기반 isolation 채점.

    beat_index 있으면 동작 단위(연속 비트 중 ref 동일 region 구간) 채점,
    없으면 고정 윈도우(5프레임) 단위 채점.
    """
    if not aligned_pairs:
        raise ValueError("aligned_pairs 가 비어 있습니다.")

    sorted_pairs = sorted(aligned_pairs, key=lambda p: (p["user_frame"], p["ref_frame"]))

    has_beat = "beat_index" in sorted_pairs[0]
    window_results = (
        _score_motion_segments(sorted_pairs)
        if has_beat
        else _score_fixed_windows(sorted_pairs)
    )

    if not window_results:
        return {
            "score": 0.0,
            "breakdown": {"error": "아이솔레이션 구간이 감지되지 않았습니다."},
            "frame_diffs": [],
        }

    scores = [w["score"] for w in window_results]
    overall = float(np.mean(scores))

    by_region: Dict[str, List[float]] = {r: [] for r in REGION_BONES}
    for w in window_results:
        r = w["ref_region"]
        if r in by_region:
            by_region[r].append(w["score"])

    region_avg = {
        r: round(float(np.mean(v)), 2) if v else None
        for r, v in by_region.items()
    }

    timing_match_ratio = round(
        sum(1 for w in window_results if w["region_match"]) / len(window_results),
        4,
    )

    worst = sorted(window_results, key=lambda x: x["score"])[:5]

    return {
        "score": round(overall, 2),
        "breakdown": {
            "scored_segments": len(window_results),
            "timing_match_ratio": timing_match_ratio,
            "by_region": region_avg,
            "worst_segments": worst,
            "scoring_mode": "motion_segment" if has_beat else "fixed_window",
        },
        "frame_diffs": window_results,
    }


# ── 하위 호환 진입점 ─────────────────────────────────────────────────

def score_from_alignment(alignment_result: Dict[str, Any]) -> Dict[str, Any]:
    pairs = alignment_result.get("pairs") or []
    result = score_isolation(pairs)
    result["alignment"] = alignment_result.get("alignment")
    return result


def score_from_json_files(
    user_json: str,
    ref_json: str,
    user_offset_sec: float = 0.0,
    ref_offset_sec: float = 0.0,
    auto_detect_start: bool = False,
    alignment_method: str = "beat",
    **align_kw: Any,
) -> Dict[str, Any]:
    aligned = align_from_paths(
        user_json,
        ref_json,
        user_offset_sec=user_offset_sec,
        ref_offset_sec=ref_offset_sec,
        auto_detect_start=auto_detect_start,
        method=alignment_method,  # type: ignore[arg-type]
        **align_kw,
    )
    return score_from_alignment(aligned)


def score_from_paths(
    user_json: str,
    ref_json: str,
    aligned_out: Optional[str] = None,
    score_out: Optional[str] = None,
    alignment_method: str = "beat",
    ref_compare_duration_sec: Optional[float] = None,
    **align_kw: Any,
) -> Dict[str, Any]:
    """align + score + 선택 저장."""
    from metrics.isolation.config import REF_COMPARE_DURATION_SEC

    if ref_compare_duration_sec is None and "ref_compare_duration_sec" not in align_kw:
        align_kw["ref_compare_duration_sec"] = REF_COMPARE_DURATION_SEC
    align_kw = {**align_kw, "method": alignment_method}
    if aligned_out:
        aligned = align_and_save(user_json, ref_json, aligned_out, **align_kw)
    else:
        aligned = align_from_paths(user_json, ref_json, **align_kw)
    result = score_from_alignment(aligned)
    if score_out:
        save_json(result, score_out)
    return result
