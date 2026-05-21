"""Rhythm scorer: 사용자 동작의 리듬 규칙성 채점 + 레퍼런스 비교 + 음악 비트 비교."""

from typing import Any, Dict, List

import numpy as np
from scipy.signal import find_peaks

# ── 장르별 키포인트 정의 ────────────────────────────────────────
# 걸그룹: 섬세한 손동작 + 팔 라인(어깨) + 발동작
# 보이그룹: 골반 아이솔레이션 + 어깨 파워 + 발동작 + 손목
# 기본: 현재 동작 (손목 + 발목)
GENRE_KEYPOINTS: Dict[str, List[str]] = {
    "girl_idol": [
        "left_wrist", "right_wrist",
        "left_shoulder", "right_shoulder",
        "left_ankle", "right_ankle",
    ],
    "boy_idol": [
        "left_hip", "right_hip",
        "left_shoulder", "right_shoulder",
        "left_ankle", "right_ankle",
        "left_wrist", "right_wrist",
    ],
    "default": [
        "left_wrist", "right_wrist",
        "left_ankle", "right_ankle",
    ],
}

VALID_GENRES = set(GENRE_KEYPOINTS.keys())

_RHYTHM_KEYPOINTS = GENRE_KEYPOINTS["girl_idol"]  # 현재 프로젝트 기본값
_MIN_PEAK_DISTANCE = 5
# 신호를 단위분산으로 정규화한 뒤 사용하는 고정 prominence — 진폭과 무관하게 동일한 기준 적용
_NORMALIZED_PROMINENCE = 0.25
_CV_SCALE = 2.0

# DTW 파라미터
_DOWNSAMPLE_FPS = 5.0        # 계산량 절감용 다운샘플 목표 FPS
_DTW_WINDOW = 50             # Sakoe-Chiba 밴드 (다운샘플 프레임 기준)
_DTW_SCALE = 2.0             # 점수 감쇠 강도 (높을수록 엄격)

# consistency는 점수에 반영하지 않고 breakdown 진단용으로만 사용
_CONSISTENCY_WEIGHT = 0.0

# 음악 비트 비교 파라미터
_BEAT_TOLERANCE_SEC = 0.2    # 비트와 동작 피크 간 허용 오차 (초)
_BEAT_HIT_WEIGHT = 0.7       # 비트 적중률 가중치
_BEAT_PRECISION_WEIGHT = 0.3 # 타이밍 정밀도 가중치
_DTW_WEIGHT = 1.0

# 통합 채점 (레퍼런스 영상 + 비트) 가중치: beat 70%, DTW 30%
_FULL_DTW_WEIGHT = 0.3
_FULL_BEAT_WEIGHT = 0.7


def _resolve_keypoints(genre: str) -> List[str]:
    return GENRE_KEYPOINTS.get(genre, GENRE_KEYPOINTS["girl_idol"])


def score_rhythm_from_extraction(
    user_extraction: Dict[str, Any],
    genre: str = "girl_idol",
) -> Dict[str, Any]:
    """추출 데이터만으로 자기일관성(리듬 규칙성) 채점."""
    fps: float = float(user_extraction.get("fps") or 30.0)
    frames: List[Dict[str, Any]] = user_extraction.get("frames") or []
    keypoints = _resolve_keypoints(genre)

    if not frames:
        return {"score": 0.0, "breakdown": {"error": "no_frames"}, "frame_diffs": []}

    signal = _velocity_signal(frames, keypoints)
    stats = _detect_peaks(signal, fps)

    peak_count = len(stats["peak_indices"])
    cv = stats["cv"]

    consistency_score = round(float(np.clip(100.0 * (1.0 - cv * _CV_SCALE), 0.0, 100.0)), 2)

    if peak_count < 4:
        reliability_penalty = (4 - peak_count) * 10.0
        consistency_score = max(0.0, consistency_score - reliability_penalty)

    tempo_bpm = round(60.0 / stats["mean_sec"], 2) if stats["mean_sec"] > 0 else 0.0

    breakdown = {
        "genre": genre,
        "keypoints_used": keypoints,
        "tempo_bpm_estimate": tempo_bpm,
        "peak_count": peak_count,
        "beat_interval_mean_sec": stats["mean_sec"],
        "beat_interval_std_sec": stats["std_sec"],
        "beat_interval_cv": cv,
        "rhythm_consistency": consistency_score,
    }
    return {"score": consistency_score, "breakdown": breakdown, "frame_diffs": []}


def score_rhythm_vs_reference(
    user_extraction: Dict[str, Any],
    ref_extraction: Dict[str, Any],
    genre: str = "girl_idol",
) -> Dict[str, Any]:
    """
    사용자 vs 레퍼런스 속도 신호를 DTW로 비교한 뒤,
    자기일관성 점수와 가중 합산하여 최종 점수 반환.

    반환: {"score": float, "breakdown": dict, "frame_diffs": list}
    """
    keypoints = _resolve_keypoints(genre)
    user_fps = float(user_extraction.get("fps") or 30.0)
    ref_fps = float(ref_extraction.get("fps") or 30.0)
    user_frames = user_extraction.get("frames") or []
    ref_frames = ref_extraction.get("frames") or []

    if len(user_frames) < 2 or len(ref_frames) < 2:
        return {"score": 0.0, "breakdown": {"error": "insufficient_frames"}, "frame_diffs": []}

    user_sig = _velocity_signal(user_frames, keypoints)
    ref_sig = _velocity_signal(ref_frames, keypoints)

    # 다운샘플 → 단위분산 정규화 (진폭 편향 제거)
    user_ds = _downsample(user_sig, user_fps, _DOWNSAMPLE_FPS)
    ref_ds = _downsample(ref_sig, ref_fps, _DOWNSAMPLE_FPS)
    user_norm = user_ds / (user_ds.std() + 1e-9)
    ref_norm = ref_ds / (ref_ds.std() + 1e-9)

    dtw_dist = _dtw_distance(user_norm, ref_norm, radius=_DTW_WINDOW)
    avg_len = (len(user_norm) + len(ref_norm)) / 2.0
    normalized_dist = dtw_dist / (avg_len + 1e-9)

    # inf/nan 방어: JSON 직렬화 불가 값을 최악 점수(worst case)로 대체
    if not np.isfinite(normalized_dist):
        normalized_dist = float(avg_len)

    dtw_score = float(np.clip(100.0 * np.exp(-normalized_dist * _DTW_SCALE), 0.0, 100.0))

    # 자기일관성 점수도 계산
    consistency_result = score_rhythm_from_extraction(user_extraction, genre=genre)
    consistency_score = consistency_result["score"]

    combined = round(
        _CONSISTENCY_WEIGHT * consistency_score + _DTW_WEIGHT * dtw_score, 2
    )

    breakdown = {
        **consistency_result["breakdown"],
        "dtw_score": round(dtw_score, 2),
        "dtw_distance_normalized": round(normalized_dist, 4),
        "consistency_score": consistency_score,
        "consistency_weight": _CONSISTENCY_WEIGHT,
        "dtw_weight": _DTW_WEIGHT,
        "user_frames_downsampled": len(user_norm),
        "ref_frames_downsampled": len(ref_norm),
    }
    return {"score": combined, "breakdown": breakdown, "frame_diffs": []}


def score_motion_vs_beats(
    user_extraction: Dict[str, Any],
    beat_data: Dict[str, Any],
    genre: str = "girl_idol",
) -> Dict[str, Any]:
    """
    사용자 동작 피크 타임과 음악 비트 타임을 비교해 채점.

    - beat_hit_rate : 비트 중 동작 피크가 허용 오차 내에 있는 비율
    - timing_precision: 적중된 비트의 평균 오차를 정밀도로 변환
    - score = 70% × hit_rate + 30% × precision

    반환: {"score": float, "breakdown": dict, "frame_diffs": list}
    """
    keypoints = _resolve_keypoints(genre)
    fps = float(user_extraction.get("fps") or 30.0)
    frames = user_extraction.get("frames") or []

    if not frames:
        return {"score": 0.0, "breakdown": {"error": "no_frames"}, "frame_diffs": []}

    beat_times: List[float] = beat_data.get("beat_times_sec") or []
    if not beat_times:
        return {"score": 0.0, "breakdown": {"error": "no_beats_detected"}, "frame_diffs": []}

    signal = _velocity_signal(frames, keypoints)
    stats = _detect_peaks(signal, fps)
    peak_times = [idx / fps for idx in stats["peak_indices"]]

    if not peak_times:
        return {
            "score": 0.0,
            "breakdown": {
                "error": "no_motion_peaks",
                "music_tempo_bpm": beat_data.get("tempo_bpm"),
                "total_beats": len(beat_times),
            },
            "frame_diffs": [],
        }

    # 각 비트에서 가장 가까운 동작 피크까지의 오차 계산
    matched = 0
    total_error = 0.0
    errors: List[float] = []

    for bt in beat_times:
        nearest_err = min(abs(bt - pt) for pt in peak_times)
        errors.append(round(nearest_err, 4))
        if nearest_err <= _BEAT_TOLERANCE_SEC:
            matched += 1
            total_error += nearest_err

    beat_hit_rate = matched / len(beat_times)
    mean_error = total_error / matched if matched > 0 else _BEAT_TOLERANCE_SEC
    precision = max(0.0, 1.0 - mean_error / _BEAT_TOLERANCE_SEC)

    score = float(np.clip(
        100.0 * (_BEAT_HIT_WEIGHT * beat_hit_rate + _BEAT_PRECISION_WEIGHT * precision),
        0.0, 100.0,
    ))

    judgment = _compute_judgment(beat_times, stats["peak_indices"], fps)

    breakdown = {
        "genre": genre,
        "keypoints_used": keypoints,
        "music_tempo_bpm": beat_data.get("tempo_bpm"),
        "total_beats": len(beat_times),
        "matched_beats": matched,
        "beat_hit_rate": round(beat_hit_rate, 4),
        "mean_timing_error_sec": round(mean_error, 4),
        "timing_precision": round(precision, 4),
        "motion_peaks_detected": len(peak_times),
        "beat_tolerance_sec": _BEAT_TOLERANCE_SEC,
        "per_beat_errors_sec": errors,
    }
    return {"score": round(score, 2), "breakdown": breakdown, "frame_diffs": [], "judgment": judgment}


def score_motion_full(
    user_extraction: Dict[str, Any],
    ref_extraction: Dict[str, Any],
    beat_data: Dict[str, Any],
    genre: str = "girl_idol",
) -> Dict[str, Any]:
    """
    레퍼런스 영상 기반 통합 채점.

    - dtw_score  (50%): 사용자 동작 패턴이 레퍼런스 동작과 얼마나 유사한가 (DTW)
    - beat_score (50%): 사용자 동작 피크가 레퍼런스 영상의 음악 비트와 얼마나 맞는가

    반환: {"score": float, "breakdown": dict, "frame_diffs": list}
    """
    dtw_result = score_rhythm_vs_reference(user_extraction, ref_extraction, genre=genre)
    beat_result = score_motion_vs_beats(user_extraction, beat_data, genre=genre)

    dtw_score = dtw_result["score"]
    beat_score = beat_result["score"]

    combined = round(
        _FULL_DTW_WEIGHT * dtw_score + _FULL_BEAT_WEIGHT * beat_score, 2
    )

    breakdown = {
        "genre": genre,
        "dtw_score": dtw_score,
        "beat_score": beat_score,
        "dtw_weight": _FULL_DTW_WEIGHT,
        "beat_weight": _FULL_BEAT_WEIGHT,
        "dtw_detail": dtw_result["breakdown"],
        "beat_detail": beat_result["breakdown"],
    }
    return {"score": combined, "breakdown": breakdown, "frame_diffs": [], "judgment": beat_result.get("judgment")}


# ──────────────────────────── 내부 유틸 ────────────────────────────

def _compute_judgment(
    beat_times: List[float],
    peak_indices: List[int],
    fps: float,
) -> Dict[str, Any]:
    """비트 vs 동작 피크 오프셋 → 타이밍 경향 + 일관성 + 피드백 문구."""
    if not beat_times or not peak_indices:
        return {
            "timing_tendency": "unknown",
            "consistency": "unknown",
            "avg_offset_ms": None,
            "std_offset_ms": None,
            "feedback": "판정을 위한 데이터가 부족합니다.",
        }

    peak_times = [idx / fps for idx in peak_indices]
    offsets_ms = [
        (min(peak_times, key=lambda pt: abs(pt - bt)) - bt) * 1000.0
        for bt in beat_times
    ]

    avg_ms = float(np.mean(offsets_ms))
    std_ms = float(np.std(offsets_ms))

    if avg_ms < -100:
        tendency = "early"
    elif avg_ms > 100:
        tendency = "late"
    else:
        tendency = "on_time"

    if std_ms < 80:
        consistency = "high"
    elif std_ms < 180:
        consistency = "moderate"
    else:
        consistency = "low"

    _tendency_text = {
        "early":   f"동작이 평균적으로 비트보다 {abs(avg_ms):.0f}ms 빠릅니다. 동작을 조금 늦게 시작하세요.",
        "late":    f"동작이 평균적으로 비트보다 {abs(avg_ms):.0f}ms 늦습니다. 반응 속도를 높이세요.",
        "on_time": "비트 타이밍이 양호합니다.",
    }
    _consistency_text = {
        "high":     "박자가 일관적입니다.",
        "moderate": "박자 일관성이 보통 수준입니다.",
        "low":      "박자가 불규칙합니다. 꾸준한 연습이 필요합니다.",
    }

    feedback = _tendency_text[tendency] + " " + _consistency_text[consistency]

    return {
        "timing_tendency": tendency,
        "consistency": consistency,
        "avg_offset_ms": round(avg_ms, 1),
        "std_offset_ms": round(std_ms, 1),
        "feedback": feedback.strip(),
    }


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

    # 단위분산 정규화 후 고정 prominence → 동작 크기와 무관하게 동일 민감도
    norm_signal = signal / (signal.std() + 1e-9)
    peaks, _ = find_peaks(norm_signal, distance=_MIN_PEAK_DISTANCE, prominence=_NORMALIZED_PROMINENCE)

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


def _downsample(signal: np.ndarray, orig_fps: float, target_fps: float) -> np.ndarray:
    step = max(1, int(round(orig_fps / target_fps)))
    return signal[::step]


def _dtw_distance(a: np.ndarray, b: np.ndarray, radius: int = 50) -> float:
    return _dtw_align(a, b, radius)[0]


def _dtw_align(
    a: np.ndarray, b: np.ndarray, radius: int = 50
) -> "tuple[float, list[tuple[int, int]]]":
    """Sakoe-Chiba 밴드 제약 DTW — 총 거리와 정렬 경로를 함께 반환.

    반환: (distance, path)
      path: [(i, j), ...] 인덱스 쌍 목록 (a[i] ↔ b[j] 대응)
    """
    n, m = len(a), len(b)
    effective_radius = max(radius, abs(n - m) + 1)

    dp = np.full((n, m), np.inf)
    dp[0, 0] = abs(float(a[0]) - float(b[0]))

    for i in range(1, min(n, effective_radius + 1)):
        dp[i, 0] = dp[i - 1, 0] + abs(float(a[i]) - float(b[0]))
    for j in range(1, min(m, effective_radius + 1)):
        dp[0, j] = dp[0, j - 1] + abs(float(a[0]) - float(b[j]))

    for i in range(1, n):
        j_lo = max(1, i - effective_radius)
        j_hi = min(m, i + effective_radius + 1)
        for j in range(j_lo, j_hi):
            cost = abs(float(a[i]) - float(b[j]))
            dp[i, j] = cost + min(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1])

    # 역추적으로 정렬 경로 복원
    path: list[tuple[int, int]] = []
    i, j = n - 1, m - 1
    while i > 0 or j > 0:
        path.append((i, j))
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            prev = min(
                (dp[i - 1, j - 1], i - 1, j - 1),
                (dp[i - 1, j],     i - 1, j),
                (dp[i,     j - 1], i,     j - 1),
            )
            i, j = prev[1], prev[2]
    path.append((0, 0))
    path.reverse()

    return float(dp[n - 1, m - 1]), path
