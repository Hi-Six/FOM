"""
동작 측면 창의성 — ref 구간 경계 매칭 + user 중간 구분(세분화) 가산.

기본: 구간 양끝이 user와 맞으면 포즈 차이와 무관 점수, 구간 내 user 추가 구분점 가산.
"""

from __future__ import annotations

from typing import Any, Literal

from .align import align_extractions, AlignmentMethod
from .activation_segment import detect_activation_boundaries_and_segments
from .creativity import score_creativity
from .motion_boundary_score import score_motion_boundary_creativity
from .pause_detect import detect_pauses_and_motion_segments
from .pause_tuning import PauseTuning
from .segment_detect import count_frames_in_time_window
from .preprocess import prepare_mirrored_frames, preprocess_window

_DEFAULT_PAUSE_MATCH_SEC = 0.15
MotionSegmentation = Literal["activation", "pause"]
MotionScoring = Literal["boundary", "pose"]
DEFAULT_MOTION_SEGMENTATION: MotionSegmentation = "activation"
DEFAULT_MOTION_SCORING: MotionScoring = "boundary"


def _detect_motion_segments(
    frames: list[dict[str, Any]],
    *,
    window_start_sec: float,
    window_end_sec: float,
    mode: MotionSegmentation,
    pause_tuning_level: int,
) -> dict[str, Any]:
    if mode == "activation":
        return detect_activation_boundaries_and_segments(
            frames,
            window_start_sec=window_start_sec,
            window_end_sec=window_end_sec,
        )
    return detect_pauses_and_motion_segments(
        frames,
        window_start_sec=window_start_sec,
        window_end_sec=window_end_sec,
        pause_tuning_level=pause_tuning_level,
    )


def _match_pauses(
    ref_pauses: list[float],
    user_pauses: list[float],
    epsilon_sec: float,
) -> dict[int, int | None]:
    used_user: set[int] = set()
    mapping: dict[int, int | None] = {}
    for ri, rt in enumerate(ref_pauses):
        best_j: int | None = None
        best_d = epsilon_sec + 1.0
        for uj, ut in enumerate(user_pauses):
            if uj in used_user:
                continue
            d = abs(float(ut) - float(rt))
            if d < best_d:
                best_d = d
                best_j = uj
        if best_j is not None and best_d <= epsilon_sec:
            mapping[ri] = best_j
            used_user.add(best_j)
        else:
            mapping[ri] = None
    return mapping


def _score_motion_pose_per_segment(
    ref_segments: list[dict[str, Any]],
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    user_window_start: float,
    user_window_end: float,
    ref_window_start: float,
    ref_window_end: float,
    delta: float,
    alignment: AlignmentMethod,
    apply_mirror: bool,
    visibility_threshold: float,
    baseline: bool,
    ref_pauses: list[float],
    pause_match: dict[int, int | None],
    tuning: PauseTuning,
    user_mirrored: list[dict[str, Any]],
    user_mirror: bool,
    ref_mirrored: list[dict[str, Any]],
    ref_mirror: bool,
    t_bar: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    """legacy: 구간별 포즈 이탈 band."""
    segment_rows: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []

    for seg in ref_segments:
        r0 = float(seg["start_sec"])
        r1 = float(seg["end_sec"])
        u0 = max(user_window_start, r0 + delta)
        u1 = min(user_window_end, r1 + delta)
        if u1 <= u0:
            u1 = min(user_window_end, u0 + 0.2)
        idx = int(seg.get("index", 0))
        skipped = False
        for i, p in enumerate(ref_pauses):
            if pause_match.get(i) is not None:
                continue
            if abs(r1 - p) <= tuning.pause_boundary_tol_sec or abs(
                r0 - p
            ) <= tuning.pause_boundary_tol_sec:
                segment_rows.append(
                    {
                        "index": idx,
                        "ref_window_sec": [r0, r1],
                        "user_window_sec": [u0, u1],
                        "skipped": True,
                        "reason": f"ref_pause_{i}_unmatched_adjacent",
                    }
                )
                skipped = True
                break
        if skipped:
            continue

        n_k = max(2, count_frames_in_time_window(ref_mirrored, r0, r1))
        user_ext = preprocess_window(
            user_raw,
            u0,
            u1,
            n_k,
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            mirrored_frames=user_mirrored,
            mirror_applied=user_mirror,
        )
        ref_ext = preprocess_window(
            ref_raw,
            r0,
            r1,
            n_k,
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            mirrored_frames=ref_mirrored,
            mirror_applied=ref_mirror,
        )
        pairs, align_meta = align_extractions(
            user_ext,
            ref_ext,
            method=alignment,
            user_offset_sec=0.0,
            ref_offset_sec=0.0,
        )
        if not pairs:
            segment_rows.append(
                {
                    "index": idx,
                    "ref_window_sec": [r0, r1],
                    "user_window_sec": [u0, u1],
                    "skipped": True,
                    "reason": "no_pairs",
                }
            )
            continue

        dtw_cost = align_meta.get("dtw_mean_cost")
        baseline_pairs = None
        baseline_dtw = None
        if baseline:
            baseline_pairs, baseline_align = align_extractions(
                ref_ext,
                ref_ext,
                method=alignment,
                user_offset_sec=0.0,
                ref_offset_sec=0.0,
            )
            baseline_dtw = baseline_align.get("dtw_mean_cost")

        creativity_seg = score_creativity(
            pairs,
            dtw_mean_cost=dtw_cost,
            baseline_pairs=baseline_pairs,
            baseline_dtw_mean_cost=baseline_dtw,
        )
        row = {
            "index": idx,
            "ref_window_sec": [round(r0, 4), round(r1, 4)],
            "user_window_sec": [round(u0, 4), round(u1, 4)],
            "duration_sec": float(seg.get("duration_sec") or (r1 - r0)),
            "alignment": align_meta,
            "creativity": creativity_seg,
            "scoring_mode": "pose",
        }
        segment_rows.append(row)
        scored.append(row)

    if not scored:
        return segment_rows, scored, 0.0
    weights = [max(1e-9, float(s.get("duration_sec") or 1.0)) for s in scored]
    scores = [float(s["creativity"]["score"]) for s in scored]
    base = sum(sc * w for sc, w in zip(scores, weights)) / sum(weights)
    return segment_rows, scored, base


def score_motion_creativity(
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    beat_grid: dict[str, Any],
    *,
    user_window_start: float,
    user_window_end: float,
    ref_window_start: float,
    ref_window_end: float,
    alignment: AlignmentMethod = "dtw",
    apply_mirror: bool = True,
    visibility_threshold: float = 0.5,
    baseline: bool = True,
    pause_match_epsilon_sec: float | None = None,
    pause_tuning_level: int = 0,
    motion_segmentation: MotionSegmentation = DEFAULT_MOTION_SEGMENTATION,
    ref_segmentation: MotionSegmentation | None = None,
    motion_scoring: MotionScoring = DEFAULT_MOTION_SCORING,
) -> dict[str, Any]:
    seg_mode: MotionSegmentation = (
        ref_segmentation if ref_segmentation is not None else motion_segmentation
    )
    tuning = PauseTuning(level=pause_tuning_level)
    t_bar = float(beat_grid.get("bar_duration_sec") or 2.0)
    base_eps = pause_match_epsilon_sec or max(
        _DEFAULT_PAUSE_MATCH_SEC,
        0.12 * t_bar,
    )
    eps = base_eps * tuning.pause_match_epsilon_scale

    ref_pause_data = _detect_motion_segments(
        ref_raw.get("frames") or [],
        window_start_sec=ref_window_start,
        window_end_sec=ref_window_end,
        mode=seg_mode,
        pause_tuning_level=pause_tuning_level,
    )
    user_pause_data = _detect_motion_segments(
        user_raw.get("frames") or [],
        window_start_sec=user_window_start,
        window_end_sec=user_window_end,
        mode=seg_mode,
        pause_tuning_level=pause_tuning_level,
    )
    ref_pauses: list[float] = ref_pause_data.get("pause_instants_sec") or []
    user_pauses: list[float] = user_pause_data.get("pause_instants_sec") or []
    ref_segments: list[dict[str, Any]] = ref_pause_data.get("motion_segments") or []

    if not ref_segments:
        ref_segments = [
            {
                "index": 0,
                "start_sec": ref_window_start,
                "end_sec": ref_window_end,
                "duration_sec": ref_window_end - ref_window_start,
            }
        ]

    pause_match = _match_pauses(ref_pauses, user_pauses, eps)
    delta = user_window_start - ref_window_start

    if motion_scoring == "boundary":
        user_seg_count = int(
            user_pause_data.get("motion_segment_count") or len(user_pauses) + 1
        )
        boundary_result = score_motion_boundary_creativity(
            ref_segments,
            ref_pauses,
            user_pauses,
            ref_window_start=ref_window_start,
            ref_window_end=ref_window_end,
            user_window_start=user_window_start,
            user_window_end=user_window_end,
            epsilon_sec=eps,
            time_delta_sec=delta,
            user_segment_count=user_seg_count,
        )
        return {
            "score": boundary_result["score"],
            "scoring_summary": boundary_result.get("scoring_summary"),
            "breakdown": {
                **boundary_result["breakdown"],
                "ref_segment_count": len(ref_segments),
                "user_segment_count": user_seg_count,
                "pause_match_epsilon_sec": round(eps, 4),
                "pause_tuning_level": tuning.level,
                "motion_segmentation": seg_mode,
                "motion_scoring": motion_scoring,
                "bar_duration_sec": t_bar,
            },
            "ref_pause_detection": ref_pause_data,
            "user_pause_detection": user_pause_data,
            "pause_match": {
                str(i): (user_pauses[j] if j is not None else None)
                for i, j in pause_match.items()
            },
            "segments": boundary_result["segments"],
            "ref_boundary_times_sec": boundary_result.get("ref_boundary_times_sec"),
            "user_boundary_times_sec": boundary_result.get("user_boundary_times_sec"),
        }

    user_mirrored, user_mirror = prepare_mirrored_frames(
        user_raw, apply_mirror=apply_mirror
    )
    ref_mirrored, ref_mirror = prepare_mirrored_frames(
        ref_raw, apply_mirror=apply_mirror
    )
    segment_rows, scored, base_score = _score_motion_pose_per_segment(
        ref_segments,
        user_raw,
        ref_raw,
        user_window_start=user_window_start,
        user_window_end=user_window_end,
        ref_window_start=ref_window_start,
        ref_window_end=ref_window_end,
        delta=delta,
        alignment=alignment,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
        baseline=baseline,
        ref_pauses=ref_pauses,
        pause_match=pause_match,
        tuning=tuning,
        user_mirrored=user_mirrored,
        user_mirror=user_mirror,
        ref_mirrored=ref_mirrored,
        ref_mirror=ref_mirror,
        t_bar=t_bar,
    )

    return {
        "score": round(min(100.0, base_score), 2),
        "breakdown": {
            "weighted_pose_score": round(base_score, 2),
            "scored_segment_count": len(scored),
            "skipped_segment_count": len(segment_rows) - len(scored),
            "pause_match_epsilon_sec": round(eps, 4),
            "pause_tuning_level": tuning.level,
            "motion_segmentation": seg_mode,
            "motion_scoring": motion_scoring,
            "bar_duration_sec": t_bar,
        },
        "ref_pause_detection": ref_pause_data,
        "user_pause_detection": user_pause_data,
        "pause_match": {
            str(i): (user_pauses[j] if j is not None else None)
            for i, j in pause_match.items()
        },
        "segments": segment_rows,
    }
