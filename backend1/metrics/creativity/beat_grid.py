"""
4비트(1마디) 박자 grid — 오디오 beat 추정.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .music_align import load_audio_mono

REL_TOL = 0.10
EPS_MS_DEFAULT = 0.065
BEATS_PER_BAR = 4


def extract_beat_grid(
    video_path: str,
    *,
    start_sec: float = 0.0,
    end_sec: float | None = None,
) -> dict[str, Any]:
    """비트·4비트 마디 경계, T_bar, T_beat."""
    import librosa

    y, sr, duration = load_audio_mono(video_path)
    win_end = duration if end_sec is None else min(float(end_sec), duration)
    win_start = max(0.0, float(start_sec))

    if len(y) < sr * 0.5:
        return _fallback_grid(win_start, win_end, reason="audio_too_short")

    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    except Exception as exc:
        return _fallback_grid(win_start, win_end, reason=f"beat_track_failed:{exc}")

    beat_times = [
        float(t)
        for t in beat_times
        if win_start <= float(t) <= win_end
    ]
    if len(beat_times) < BEATS_PER_BAR + 1:
        return _fallback_grid(win_start, win_end, reason="too_few_beats")

    tempo_val = float(np.atleast_1d(tempo)[0])
    beat_intervals = np.diff(beat_times)
    t_beat = float(np.median(beat_intervals)) if len(beat_intervals) else 60.0 / max(tempo_val, 1.0)
    t_bar = t_beat * BEATS_PER_BAR

    bar_starts: list[float] = []
    for i in range(0, len(beat_times) - BEATS_PER_BAR + 1, BEATS_PER_BAR):
        bar_starts.append(round(beat_times[i], 4))
    if bar_starts and bar_starts[-1] + t_bar < win_end - t_beat * 0.5:
        t = bar_starts[-1] + t_beat * BEATS_PER_BAR
        while t < win_end:
            bar_starts.append(round(t, 4))
            t += t_beat * BEATS_PER_BAR

    bars: list[dict[str, Any]] = []
    for i, bs in enumerate(bar_starts):
        be = min(win_end, bs + t_bar) if i + 1 >= len(bar_starts) else bar_starts[i + 1]
        if be - bs >= t_beat * 0.5:
            bars.append(
                {
                    "index": i,
                    "start_sec": round(bs, 4),
                    "end_sec": round(be, 4),
                    "duration_sec": round(be - bs, 4),
                }
            )

    if not bars:
        return _fallback_grid(win_start, win_end, reason="no_bars")

    return {
        "method": "librosa_beat_4",
        "tempo_bpm": round(tempo_val, 2),
        "beat_times_sec": [round(t, 4) for t in beat_times[:200]],
        "bar_duration_sec": round(t_bar, 4),
        "beat_duration_sec": round(t_beat, 4),
        "bars": bars,
        "window_start_sec": round(win_start, 4),
        "window_end_sec": round(win_end, 4),
        "rel_tol": REL_TOL,
        "eps_ms": EPS_MS_DEFAULT,
        "beats_per_bar": BEATS_PER_BAR,
    }


def _fallback_grid(
    start_sec: float,
    end_sec: float,
    *,
    reason: str,
) -> dict[str, Any]:
    dur = max(0.5, end_sec - start_sec)
    t_bar = 2.0
    t_beat = t_bar / BEATS_PER_BAR
    bars: list[dict[str, Any]] = []
    t = start_sec
    i = 0
    while t < end_sec - t_beat:
        be = min(end_sec, t + t_bar)
        bars.append(
            {
                "index": i,
                "start_sec": round(t, 4),
                "end_sec": round(be, 4),
                "duration_sec": round(be - t, 4),
            }
        )
        t += t_bar
        i += 1
    return {
        "method": "fallback_fixed_bar",
        "tempo_bpm": round(60.0 * BEATS_PER_BAR / t_bar, 2),
        "bar_duration_sec": t_bar,
        "beat_duration_sec": t_beat,
        "bars": bars,
        "window_start_sec": round(start_sec, 4),
        "window_end_sec": round(end_sec, 4),
        "rel_tol": REL_TOL,
        "eps_ms": EPS_MS_DEFAULT,
        "beats_per_bar": BEATS_PER_BAR,
        "fallback_reason": reason,
    }


def duration_matches_target(
    duration_sec: float,
    target_sec: float,
    *,
    rel_tol: float = REL_TOL,
    eps_sec: float = EPS_MS_DEFAULT,
) -> bool:
    if target_sec <= 1e-9 or duration_sec <= 1e-9:
        return False
    low = max(target_sec * (1.0 - rel_tol), target_sec - eps_sec)
    high = min(target_sec * (1.0 + rel_tol), target_sec + eps_sec)
    return low <= duration_sec <= high


ALLOWED_BAR_MULTIPLES = (1.0, 2.0, 3.0, 4.0, 0.5, 1.0 / 3.0, 1.0 / 4.0)


def best_matching_multiple(duration_sec: float, t_bar: float) -> float | None:
    """duration ≈ k * T_bar 인 허용 k 반환, 없으면 None."""
    if t_bar <= 1e-9:
        return None
    eps = EPS_MS_DEFAULT
    rel = REL_TOL
    ratio = duration_sec / t_bar
    for k in ALLOWED_BAR_MULTIPLES:
        target = k * t_bar
        if duration_matches_target(duration_sec, target, rel_tol=rel, eps_sec=eps):
            return k
    return None
