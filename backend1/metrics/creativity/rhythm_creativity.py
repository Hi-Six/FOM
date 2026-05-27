"""
박자 측면 창의성 — 멈춤 간격이 n마디(4비트) 주기와 맞는지.
기본기 점수 없음.
"""

from __future__ import annotations

from typing import Any

from .beat_grid import ALLOWED_BAR_MULTIPLES, best_matching_multiple
from .pause_detect import detect_pauses_and_motion_segments


def score_rhythm_creativity(
    frames: list[dict[str, Any]],
    beat_grid: dict[str, Any],
    *,
    window_start_sec: float,
    window_end_sec: float,
    stream_label: str = "dancer",
    pause_tuning_level: int = 0,
) -> dict[str, Any]:
    """
    멈춤 시점 간격 Δt 를 T_bar 배수 {1,2,3,4,1/2,1/3,1/4} ±10% + ε_ms 와 비교.
    점수 = 100 × (매칭 간격 수 / 전체 간격 수).
    """
    t_bar = float(beat_grid.get("bar_duration_sec") or 2.0)
    pause_data = detect_pauses_and_motion_segments(
        frames,
        window_start_sec=window_start_sec,
        window_end_sec=window_end_sec,
        pause_tuning_level=pause_tuning_level,
    )
    pauses = pause_data.get("pause_instants_sec") or []

    intervals: list[dict[str, Any]] = []
    bounds = [window_start_sec] + list(pauses) + [window_end_sec]
    for i in range(len(bounds) - 1):
        dt = float(bounds[i + 1]) - float(bounds[i])
        if dt < 0.05:
            continue
        k = best_matching_multiple(dt, t_bar)
        intervals.append(
            {
                "start_sec": round(bounds[i], 4),
                "end_sec": round(bounds[i + 1], 4),
                "duration_sec": round(dt, 4),
                "duration_bars": round(dt / t_bar, 4) if t_bar > 0 else None,
                "matched_multiple": k,
                "matched": k is not None,
            }
        )

    # 멈춤 사이 간격만 (양 끝 window 경계 제외한 순수 pause 간격)
    pause_only_intervals: list[dict[str, Any]] = []
    for i in range(len(pauses) - 1):
        dt = float(pauses[i + 1]) - float(pauses[i])
        if dt < 0.05:
            continue
        k = best_matching_multiple(dt, t_bar)
        pause_only_intervals.append(
            {
                "from_pause_sec": pauses[i],
                "to_pause_sec": pauses[i + 1],
                "duration_sec": round(dt, 4),
                "duration_bars": round(dt / t_bar, 4),
                "matched_multiple": k,
                "matched": k is not None,
            }
        )

    eval_intervals = pause_only_intervals if len(pause_only_intervals) >= 1 else intervals
    if not eval_intervals:
        return {
            "score": 0.0,
            "stream": stream_label,
            "breakdown": {
                "reason": "no_pause_intervals",
                "pause_count": len(pauses),
                "allowed_multiples": list(ALLOWED_BAR_MULTIPLES),
            },
            "pause_detection": pause_data,
            "intervals": intervals,
        }

    matched = sum(1 for x in eval_intervals if x.get("matched"))
    total = len(eval_intervals)
    score = round(100.0 * matched / total, 2)

    motion_bonus_hits: list[dict[str, Any]] = []
    for seg in pause_data.get("motion_segments") or []:
        dur = float(seg.get("duration_sec") or 0)
        k = best_matching_multiple(dur, t_bar)
        if k is not None:
            motion_bonus_hits.append(
                {
                    "segment_index": seg.get("index"),
                    "start_sec": seg.get("start_sec"),
                    "end_sec": seg.get("end_sec"),
                    "duration_sec": dur,
                    "matched_multiple": k,
                    "note": "motion_segment_length_vs_bar",
                }
            )

    return {
        "score": score,
        "stream": stream_label,
        "breakdown": {
            "matched_intervals": matched,
            "total_intervals": total,
            "bar_duration_sec": t_bar,
            "allowed_multiples": list(ALLOWED_BAR_MULTIPLES),
            "pause_count": len(pauses),
            "motion_length_matches": len(motion_bonus_hits),
        },
        "pause_detection": pause_data,
        "pause_intervals": pause_only_intervals,
        "intervals": intervals,
        "motion_length_matches": motion_bonus_hits,
    }
