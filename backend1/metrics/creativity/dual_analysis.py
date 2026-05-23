"""
동작(motion) 중심 창의성 분석. (박자 rhythm은 analysis_mode=rhythm 일 때만 별도 채점)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .beat_grid import extract_beat_grid
from .motion_creativity import (
    DEFAULT_MOTION_SCORING,
    DEFAULT_MOTION_SEGMENTATION,
    score_motion_creativity,
)
from .rhythm_creativity import score_rhythm_creativity

AnalysisMode = Literal["legacy", "rhythm", "motion", "both"]


def _window_end(frames: list[dict], offset: float, end: float | None) -> float:
    if end is not None:
        return float(end)
    if not frames:
        return offset
    return float(max(float(f.get("time_sec", 0.0)) for f in frames))


def analyze_dual_creativity(
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    audio_video_path: str,
    user_offset_sec: float,
    ref_offset_sec: float,
    user_end_sec: float | None,
    ref_end_sec: float | None,
    alignment: str = "dtw",
    apply_mirror: bool = True,
    visibility_threshold: float = 0.5,
    baseline: bool = True,
    analysis_mode: AnalysisMode = "motion",
    stream_labels: tuple[str, str] | None = None,
    pause_tuning_level: int = 0,
    motion_segmentation: str = DEFAULT_MOTION_SEGMENTATION,
    motion_scoring: str = DEFAULT_MOTION_SCORING,
) -> dict[str, Any]:
    """
    motion(기본): ref/user 경계 매칭·세분화 → 창의성 점수.
    rhythm: 멈춤 간격 n마디 (별도 모드, 최종 점수에 미포함).
    both: motion과 동일 (하위 호환).
    """
    effective_mode: AnalysisMode = (
        "motion" if analysis_mode == "both" else analysis_mode
    )
    user_frames = user_raw.get("frames") or []
    ref_frames = ref_raw.get("frames") or []
    u0 = float(user_offset_sec)
    r0 = float(ref_offset_sec)
    u_end = _window_end(user_frames, u0, user_end_sec)
    r_end = _window_end(ref_frames, r0, ref_end_sec)
    win_end = max(u_end, r_end)

    beat_grid = extract_beat_grid(
        audio_video_path,
        start_sec=min(u0, r0),
        end_sec=win_end,
    )

    label_user, label_ref = stream_labels or ("user", "reference")
    rhythm_out: dict[str, Any] = {}
    motion_out: dict[str, Any] | None = None

    if effective_mode == "rhythm":
        rhythm_out[label_user] = score_rhythm_creativity(
            user_frames,
            beat_grid,
            window_start_sec=u0,
            window_end_sec=u_end,
            stream_label=label_user,
            pause_tuning_level=pause_tuning_level,
        )
        rhythm_out[label_ref] = score_rhythm_creativity(
            ref_frames,
            beat_grid,
            window_start_sec=r0,
            window_end_sec=r_end,
            stream_label=label_ref,
            pause_tuning_level=pause_tuning_level,
        )
        scores = [float(rhythm_out[k]["score"]) for k in rhythm_out]
        rhythm_out["aggregate_score"] = round(sum(scores) / len(scores), 2) if scores else 0.0

    if effective_mode == "motion":
        motion_out = score_motion_creativity(
            user_raw,
            ref_raw,
            beat_grid,
            user_window_start=u0,
            user_window_end=u_end,
            ref_window_start=r0,
            ref_window_end=r_end,
            alignment=alignment,  # type: ignore[arg-type]
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            baseline=baseline,
            pause_tuning_level=pause_tuning_level,
            motion_segmentation=motion_segmentation,  # type: ignore[arg-type]
            motion_scoring=motion_scoring,  # type: ignore[arg-type]
        )

    motion_score = (
        float(motion_out["score"])
        if motion_out and motion_out.get("score") is not None
        else None
    )
    rhythm_score = rhythm_out.get("aggregate_score")
    if effective_mode == "motion":
        combined = round(motion_score, 2) if motion_score is not None else 0.0
        score_source = "motion"
    elif effective_mode == "rhythm":
        combined = round(float(rhythm_score), 2) if rhythm_score is not None else 0.0
        score_source = "rhythm"
    else:
        combined = 0.0
        score_source = "none"

    return {
        "analysis_mode": effective_mode,
        "beat_grid": beat_grid,
        "rhythm": rhythm_out if rhythm_out else None,
        "motion": motion_out,
        "score": combined,
        "breakdown": {
            "score_source": score_source,
            "motion_score": motion_score,
            "rhythm_aggregate": rhythm_score,
            "rhythm_excluded_from_creativity": effective_mode == "motion",
            "pause_tuning_level": pause_tuning_level,
            "motion_segmentation": motion_segmentation,
            "motion_scoring": motion_scoring,
        },
    }
