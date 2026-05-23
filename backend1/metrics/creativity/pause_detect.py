"""

멈춤 시점(1프레임) + 동작 구간(멈춤 사이) 검출 — 히스테리시스 속도.

전신 정지 규칙은 사용하지 않음 (6관절 합성 속도).

"""



from __future__ import annotations



from typing import Any



import numpy as np



from .pause_tuning import PauseTuning



_MOTION_KEYPOINTS = (

    "left_wrist",

    "right_wrist",

    "left_ankle",

    "right_ankle",

    "left_shoulder",

    "right_shoulder",

)



_DEFAULT_MIN_MOTION_SEC = 0.25

_MIN_PAUSE_GAP_SEC = 0.08





def _velocity_signal(frames: list[dict[str, Any]], keypoints: tuple[str, ...]) -> np.ndarray:

    positions: list[np.ndarray] = []

    for frame in frames:

        lm = frame.get("normalized_landmarks") or {}

        coords: list[float] = []

        for kp in keypoints:

            pt = lm.get(kp)

            if pt:

                coords.extend([float(pt["x"]), float(pt["y"])])

        positions.append(

            np.array(coords, dtype=float) if coords else np.zeros(len(keypoints) * 2)

        )

    if len(positions) < 2:

        return np.zeros(max(len(positions), 1))

    pos_arr = np.array(positions)

    diffs = np.linalg.norm(np.diff(pos_arr, axis=0), axis=1)

    return np.concatenate([[0.0], diffs])





def _auto_thresholds(

    velocity: np.ndarray,

    tuning: PauseTuning,

) -> tuple[float, float]:

    nz = velocity[velocity > 1e-9]

    if len(nz) == 0:

        t_low, t_high = 0.008, 0.012

    else:

        p25 = float(np.percentile(nz, 25))

        p50 = float(np.percentile(nz, 50))

        if tuning.relaxed_thresholds:

            t_low = max(0.005, min(0.025, p25 * 0.7))

            t_high = max(t_low * 1.25, min(0.024, p50 * 0.55))

        else:

            t_low = max(0.005, min(0.018, p25 * 0.5))

            t_high = max(t_low * 1.35, min(0.028, p50 * 0.75))

    if tuning.extra_low_boost:

        t_low = min(0.03, t_low * 1.12)

        t_high = max(t_low * 1.2, t_high * 0.92)

    return t_low, t_high





def _pauses_hysteresis(

    velocity: np.ndarray,

    times: list[float],

    t_low: float,

    t_high: float,

    *,

    entry_prev_min: float,

) -> list[float]:

    pause_times: list[float] = []

    state = "high"

    for i in range(1, len(velocity)):

        v = float(velocity[i])

        t = times[i]

        if state == "high" and v < t_low:

            if i > 0 and float(velocity[i - 1]) >= entry_prev_min:

                pause_times.append(round(t, 4))

            state = "low"

        elif state == "low" and v > t_high:

            state = "high"

    return pause_times





def _pauses_run_based(

    velocity: np.ndarray,

    times: list[float],

    t_low: float,

    t_high: float,

    *,

    min_run: int,

    entry_prev_min: float,

) -> list[float]:

    """연속 min_run 프레임 저속 + 직전 프레임은 entry_prev_min 이상."""

    n = len(velocity)

    pause_times: list[float] = []

    i = 1

    while i < n:

        if float(velocity[i]) >= t_low:

            i += 1

            continue

        j = i

        while j < n and float(velocity[j]) < t_low:

            j += 1

        run_len = j - i

        if run_len >= min_run and i > 0 and float(velocity[i - 1]) >= entry_prev_min:

            pause_times.append(round(times[i], 4))

        i = max(j, i + 1)

    return pause_times





def _merge_pauses(pause_times: list[float], min_gap_sec: float) -> list[float]:

    merged: list[float] = []

    for t in pause_times:

        if merged and t - merged[-1] < min_gap_sec:

            continue

        merged.append(t)

    return merged





def detect_pauses_and_motion_segments(

    frames: list[dict[str, Any]],

    *,

    window_start_sec: float,

    window_end_sec: float,

    min_motion_sec: float | None = None,

    velocity_threshold_low: float | None = None,

    velocity_threshold_high: float | None = None,

    pause_tuning_level: int = 0,

) -> dict[str, Any]:

    """

    멈춤: 저속 진입 시점(히스테리시스 또는 연속 N프레임).

    동작 구간: 연속 멈춤 사이 [t_i, t_{i+1}] (최소 길이 min_motion_sec).

    """

    tuning = PauseTuning(level=pause_tuning_level)

    min_motion = (

        float(min_motion_sec)

        if min_motion_sec is not None

        else tuning.min_motion_sec

    )

    min_gap = tuning.min_pause_gap_sec



    pool = [

        f

        for f in frames

        if window_start_sec <= float(f.get("time_sec", 0.0)) <= window_end_sec

    ]

    if len(pool) < 3:

        return {

            "pause_instants_sec": [],

            "motion_segments": [],

            "error": "too_few_frames",

        }



    velocity = _velocity_signal(pool, _MOTION_KEYPOINTS)

    t_low, t_high = _auto_thresholds(velocity, tuning)

    if velocity_threshold_low is not None:

        t_low = float(velocity_threshold_low)

    if velocity_threshold_high is not None:

        t_high = float(velocity_threshold_high)

    if t_high <= t_low:

        t_high = t_low * 1.4



    times = [float(f.get("time_sec", 0.0)) for f in pool]

    entry_prev_min = t_low if tuning.run_based_pauses else t_high



    if tuning.run_based_pauses:

        pause_times = _pauses_run_based(

            velocity,

            times,

            t_low,

            t_high,

            min_run=tuning.pause_min_run_frames,

            entry_prev_min=entry_prev_min,

        )

    else:

        pause_times = _pauses_hysteresis(

            velocity,

            times,

            t_low,

            t_high,

            entry_prev_min=entry_prev_min,

        )



    merged_pauses = _merge_pauses(pause_times, min_gap)



    bounds = [window_start_sec] + merged_pauses + [window_end_sec]

    motion_segments: list[dict[str, Any]] = []

    for i in range(len(bounds) - 1):

        t0, t1 = float(bounds[i]), float(bounds[i + 1])

        if t1 - t0 < min_motion:

            continue

        motion_segments.append(

            {

                "index": len(motion_segments),

                "start_sec": round(t0, 4),

                "end_sec": round(t1, 4),

                "duration_sec": round(t1 - t0, 4),

            }

        )



    return {

        "pause_instants_sec": merged_pauses,

        "motion_segments": motion_segments,

        "velocity_threshold_low": round(t_low, 6),

        "velocity_threshold_high": round(t_high, 6),

        "frame_count": len(pool),

        "pause_count": len(merged_pauses),

        "motion_segment_count": len(motion_segments),

        "pause_tuning_level": tuning.level,

        "min_pause_gap_sec": min_gap,

        "min_motion_sec": min_motion,

    }


