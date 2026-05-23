"""
창의성 metric 전체 파이프라인 — CLI·HTTP API 공용.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .accuracy import score_accuracy
from .align import align_extractions
from .creativity import score_creativity
from .extract import extract_from_media, is_image_path, save_extraction
from .music_align import resolve_music_offsets
from .preprocess import (
    prepare_mirrored_frames,
    preprocess_extraction,
    preprocess_window,
    resolve_offset_sec,
)
from .dual_analysis import AnalysisMode, analyze_dual_creativity
from .motion_creativity import DEFAULT_MOTION_SCORING, DEFAULT_MOTION_SEGMENTATION
from .segment_detect import (
    aggregate_segment_creativity_scores,
    build_creativity_timing_summary,
    count_frames_in_time_window,
    detect_ref_segments,
    enrich_frame_diffs_with_times,
    extract_peak_divergence_windows,
    map_segment_to_user_time,
)

AlignmentMethod = Literal["index", "time", "dtw"]

_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
_DEFAULT_SAVE_DIR = _OUTPUT_ROOT / "extractions"
_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def ensure_output_dirs() -> None:
    _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    _DEFAULT_SAVE_DIR.mkdir(parents=True, exist_ok=True)


def _is_image_extraction(extraction: dict[str, Any]) -> bool:
    return extraction.get("media_type") == "image" or len(extraction.get("frames") or []) <= 1


def _path_is_video_file(path: str | None) -> bool:
    if not path:
        return False
    try:
        p = Path(path)
        return p.is_file() and p.suffix.lower() in _VIDEO_SUFFIXES
    except OSError:
        return False


def resolve_creativity_video_sources(
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    user_source: str,
    ref_source: str,
    user_video_path: str | None = None,
) -> tuple[str, str, bool]:
    """
    두 영상 비교용 media 경로. beat_grid·music_align에 쓸 수 있는 mp4가 있으면 True.
    """
    paths: list[str] = []
    for candidate in (
        user_video_path,
        user_raw.get("source"),
        ref_raw.get("source"),
        user_source,
        ref_source,
    ):
        if candidate and _path_is_video_file(str(candidate)):
            s = str(candidate)
            if s not in paths:
                paths.append(s)
    if not paths:
        return user_source, ref_source, False
    user_p = paths[0]
    ref_p = paths[1] if len(paths) > 1 else paths[0]
    return user_p, ref_p, True


def score_creativity_media_pair_from_extractions(
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    user_source: str,
    ref_source: str,
    user_video_path: str | None = None,
    user_offset_sec: float = 0.0,
    ref_offset_sec: float = 0.0,
    auto_detect_start: bool = False,
    music_align: bool = True,
    alignment: AlignmentMethod = "dtw",
    apply_mirror: bool = True,
    visibility_threshold: float = 0.5,
    baseline: bool = True,
    pause_tuning_level: int = 0,
    motion_segmentation: str = DEFAULT_MOTION_SEGMENTATION,
    motion_scoring: str = DEFAULT_MOTION_SCORING,
    analysis_mode: AnalysisMode = "motion",
) -> dict[str, Any]:
    """
    저장된 user/ref 추출 JSON → 기본 창의성 채점(동작 경계 매칭).
    통합 /video/analyze 오케스트레이터·metric API 공용.
    """
    user_media, ref_media, has_video = resolve_creativity_video_sources(
        user_raw,
        ref_raw,
        user_source=user_source,
        ref_source=ref_source,
        user_video_path=user_video_path,
    )
    payload = analyze_extraction_pair(
        user_raw,
        ref_raw,
        user_source=user_media,
        ref_source=ref_media,
        user_offset_sec=user_offset_sec,
        ref_offset_sec=ref_offset_sec,
        auto_detect_start=auto_detect_start,
        music_align=music_align and has_video,
        baseline=baseline,
        alignment=alignment,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
        analysis_mode=analysis_mode,
        pause_tuning_level=pause_tuning_level,
        motion_segmentation=motion_segmentation,
        motion_scoring=motion_scoring,
    )
    creativity = payload.get("creativity") or {}
    motion = payload.get("motion") or creativity.get("motion")
    breakdown = dict(creativity.get("breakdown") or {})
    breakdown["pipeline"] = payload.get("inputs", {}).get("pipeline", "motion")
    breakdown["analysis_mode"] = payload.get("inputs", {}).get(
        "analysis_mode", analysis_mode
    )
    if motion:
        breakdown["motion_scoring_summary"] = motion.get("scoring_summary")
    return {
        "score": creativity.get("score", 0.0),
        "breakdown": breakdown,
        "motion": motion,
        "beat_grid": payload.get("beat_grid"),
        "music_align": payload.get("music_align"),
        "inputs": payload.get("inputs"),
    }


def _resolve_video_windows(
    user_p: Path,
    ref_p: Path,
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    music_align: bool,
    user_offset_sec: float,
    ref_offset_sec: float,
    auto_detect_start: bool,
) -> tuple[float, float | None, float, float | None, dict[str, Any] | None, bool]:
    user_offset = 0.0
    ref_offset = 0.0
    user_end: float | None = None
    ref_end: float | None = None
    music_info: dict[str, Any] | None = None
    use_music = False
    manual_offset = user_offset_sec != 0.0 or ref_offset_sec != 0.0
    if music_align and not manual_offset and not auto_detect_start:
        use_music = True
        user_offset, user_end, ref_offset, ref_end, music_info = resolve_music_offsets(
            str(user_p),
            str(ref_p),
            use_music_align=True,
        )
    else:
        user_offset = resolve_offset_sec(
            user_raw.get("frames") or [],
            user_offset_sec,
            auto_detect_start,
        )
        ref_offset = resolve_offset_sec(
            ref_raw.get("frames") or [],
            ref_offset_sec,
            auto_detect_start,
        )
    return user_offset, user_end, ref_offset, ref_end, music_info, use_music


def _analyze_image_pair(
    user_p: Path,
    ref_p: Path,
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    baseline: bool,
    with_accuracy: bool,
    with_llm_adjustment: bool,
    apply_mirror: bool,
    visibility_threshold: float,
    save_extractions: bool,
    save_dir: Path | None,
    extra_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """이미지 1장 쌍 — 단일 프레임 비교."""
    user_ext = preprocess_extraction(
        user_raw,
        1,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
    )
    ref_ext = preprocess_extraction(
        ref_raw,
        1,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
    )

    if save_extractions:
        ensure_output_dirs()
        out_dir = save_dir or _DEFAULT_SAVE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        save_extraction(user_ext, out_dir / "user.creativity.json")
        save_extraction(ref_ext, out_dir / "reference.creativity.json")

    pairs, align_meta = align_extractions(
        user_ext,
        ref_ext,
        method="index",
        user_offset_sec=0.0,
        ref_offset_sec=0.0,
    )
    if not pairs:
        raise ValueError("비교할 프레임이 없습니다. 포즈·visibility를 확인하세요.")

    baseline_pairs = None
    baseline_dtw: float | None = None
    if baseline:
        baseline_pairs, baseline_align = align_extractions(
            ref_ext,
            ref_ext,
            method="index",
            user_offset_sec=0.0,
            ref_offset_sec=0.0,
        )
        baseline_dtw = baseline_align.get("dtw_mean_cost")

    creativity_result = score_creativity(
        pairs,
        baseline_pairs=baseline_pairs,
        baseline_dtw_mean_cost=baseline_dtw,
    )
    if with_llm_adjustment:
        from .llm_creativity import apply_llm_hybrid_to_creativity

        creativity_result = apply_llm_hybrid_to_creativity(creativity_result)

    inputs: dict[str, Any] = {
        "user": str(user_p),
        "reference": str(ref_p),
        "media_type": "image",
        "segment_mode": False,
        "alignment": "index",
        "apply_mirror": apply_mirror,
        "visibility_threshold": visibility_threshold,
        "baseline": baseline,
        "with_accuracy": with_accuracy,
        "with_llm_adjustment": with_llm_adjustment,
    }
    if extra_inputs:
        inputs.update(extra_inputs)

    payload: dict[str, Any] = {
        "inputs": inputs,
        "preprocess": {
            "user": user_ext.get("preprocess"),
            "reference": ref_ext.get("preprocess"),
        },
        "alignment": align_meta,
        "creativity": creativity_result,
        "extractions_sampled": {
            "user": user_ext.get("frames") or [],
            "reference": ref_ext.get("frames") or [],
        },
    }
    if with_accuracy:
        payload["accuracy"] = score_accuracy(
            pairs,
            reference_pairs=baseline_pairs,
            reference_dtw_mean_cost=baseline_dtw,
        )
    return payload


def analyze_extraction_pair(
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    user_source: str,
    ref_source: str,
    user_offset_sec: float = 0.0,
    ref_offset_sec: float = 0.0,
    auto_detect_start: bool = False,
    music_align: bool = True,
    baseline: bool = True,
    with_accuracy: bool = False,
    with_llm_adjustment: bool = False,
    alignment: AlignmentMethod = "dtw",
    apply_mirror: bool = True,
    visibility_threshold: float = 0.5,
    save_extractions: bool = False,
    save_dir: Path | None = None,
    num_motion_units: int = 3,
    idle_min_frames: int = 3,
    motion_velocity_threshold: float | None = None,
    min_blend_weight: float = 0.15,
    analysis_mode: AnalysisMode = "motion",
    extra_inputs: dict[str, Any] | None = None,
    pause_tuning_level: int = 0,
    motion_segmentation: str = DEFAULT_MOTION_SEGMENTATION,
    motion_scoring: str = DEFAULT_MOTION_SCORING,
) -> dict[str, Any]:
    """이미 추출된 user/ref JSON — 영상: motion(기본) 또는 legacy."""
    user_p = Path(user_source)
    ref_p = Path(ref_source)

    if _is_image_extraction(user_raw) and _is_image_extraction(ref_raw):
        return _analyze_image_pair(
            user_p,
            ref_p,
            user_raw,
            ref_raw,
            baseline=baseline,
            with_accuracy=with_accuracy,
            with_llm_adjustment=with_llm_adjustment,
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            save_extractions=save_extractions,
            save_dir=save_dir,
            extra_inputs=extra_inputs,
        )

    if analysis_mode != "legacy":
        return _analyze_dual_mode(
            user_p,
            ref_p,
            user_raw,
            ref_raw,
            music_align=music_align,
            user_offset_sec=user_offset_sec,
            ref_offset_sec=ref_offset_sec,
            auto_detect_start=auto_detect_start,
            baseline=baseline,
            with_accuracy=with_accuracy,
            with_llm_adjustment=with_llm_adjustment,
            alignment=alignment,
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            save_extractions=save_extractions,
            save_dir=save_dir,
            analysis_mode=analysis_mode,
            extra_inputs=extra_inputs,
            pause_tuning_level=pause_tuning_level,
            motion_segmentation=motion_segmentation,
            motion_scoring=motion_scoring,
        )

    return _analyze_segment_mode(
        user_p,
        ref_p,
        user_raw,
        ref_raw,
        music_align=music_align,
        user_offset_sec=user_offset_sec,
        ref_offset_sec=ref_offset_sec,
        auto_detect_start=auto_detect_start,
        baseline=baseline,
        with_accuracy=with_accuracy,
        with_llm_adjustment=with_llm_adjustment,
        alignment=alignment,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
        save_extractions=save_extractions,
        save_dir=save_dir,
        num_motion_units=num_motion_units,
        idle_min_frames=idle_min_frames,
        motion_velocity_threshold=motion_velocity_threshold,
        min_blend_weight=min_blend_weight,
        extra_inputs=extra_inputs,
    )


def analyze_media_pair(
    user_path: str | Path,
    reference_path: str | Path,
    *,
    user_offset_sec: float = 0.0,
    ref_offset_sec: float = 0.0,
    auto_detect_start: bool = False,
    music_align: bool = True,
    baseline: bool = True,
    with_accuracy: bool = False,
    with_llm_adjustment: bool = False,
    alignment: AlignmentMethod = "dtw",
    apply_mirror: bool = True,
    visibility_threshold: float = 0.5,
    save_extractions: bool = False,
    save_dir: Path | None = None,
    num_motion_units: int = 3,
    idle_min_frames: int = 3,
    motion_velocity_threshold: float | None = None,
    min_blend_weight: float = 0.15,
    analysis_mode: AnalysisMode = "motion",
    pause_tuning_level: int = 0,
    motion_segmentation: str = DEFAULT_MOTION_SEGMENTATION,
    motion_scoring: str = DEFAULT_MOTION_SCORING,
) -> dict[str, Any]:
    """
    사용자·레퍼런스 미디어 쌍 → 창의성 점수.
    영상: analysis_mode motion(기본)=동작 경계 채점, legacy=구 motion_idle n구간.

    Raises:
        ValueError: 입력/미디어/비교 불가
        FileNotFoundError: 경로 없음
    """
    user_p = Path(user_path)
    ref_p = Path(reference_path)
    if not user_p.is_file():
        raise FileNotFoundError(f"사용자 파일이 없습니다: {user_p}")
    if not ref_p.is_file():
        raise FileNotFoundError(f"레퍼런스 파일이 없습니다: {ref_p}")

    user_is_image = is_image_path(user_p)
    ref_is_image = is_image_path(ref_p)
    if user_is_image != ref_is_image:
        raise ValueError("사용자·레퍼런스는 둘 다 영상이거나 둘 다 이미지여야 합니다.")

    user_raw = extract_from_media(str(user_p))
    ref_raw = extract_from_media(str(ref_p))

    if user_is_image:
        return _analyze_image_pair(
            user_p,
            ref_p,
            user_raw,
            ref_raw,
            baseline=baseline,
            with_accuracy=with_accuracy,
            with_llm_adjustment=with_llm_adjustment,
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            save_extractions=save_extractions,
            save_dir=save_dir,
        )

    return analyze_extraction_pair(
        user_raw,
        ref_raw,
        user_source=str(user_p),
        ref_source=str(ref_p),
        user_offset_sec=user_offset_sec,
        ref_offset_sec=ref_offset_sec,
        auto_detect_start=auto_detect_start,
        music_align=music_align,
        baseline=baseline,
        with_accuracy=with_accuracy,
        with_llm_adjustment=with_llm_adjustment,
        alignment=alignment,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
        save_extractions=save_extractions,
        save_dir=save_dir,
        num_motion_units=num_motion_units,
        idle_min_frames=idle_min_frames,
        motion_velocity_threshold=motion_velocity_threshold,
        min_blend_weight=min_blend_weight,
        analysis_mode=analysis_mode,
        pause_tuning_level=pause_tuning_level,
        motion_segmentation=motion_segmentation,
        motion_scoring=motion_scoring,
    )


def _analyze_dual_mode(
    user_p: Path,
    ref_p: Path,
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    music_align: bool,
    user_offset_sec: float,
    ref_offset_sec: float,
    auto_detect_start: bool,
    baseline: bool,
    with_accuracy: bool,
    with_llm_adjustment: bool,
    alignment: AlignmentMethod,
    apply_mirror: bool,
    visibility_threshold: float,
    save_extractions: bool,
    save_dir: Path | None,
    analysis_mode: AnalysisMode,
    extra_inputs: dict[str, Any] | None = None,
    pause_tuning_level: int = 0,
    motion_segmentation: str = DEFAULT_MOTION_SEGMENTATION,
    motion_scoring: str = DEFAULT_MOTION_SCORING,
) -> dict[str, Any]:
    user_offset, user_end, ref_offset, ref_end, music_info, use_music = _resolve_video_windows(
        user_p,
        ref_p,
        user_raw,
        ref_raw,
        music_align=music_align,
        user_offset_sec=user_offset_sec,
        ref_offset_sec=ref_offset_sec,
        auto_detect_start=auto_detect_start,
    )

    audio_path = str(ref_p)
    if user_p.resolve() == ref_p.resolve():
        audio_path = str(user_p)

    stream_labels = None
    if extra_inputs and extra_inputs.get("mode") == "split_screen":
        split = extra_inputs
        up = split.get("user_panel", "left")
        stream_labels = (
            ("left", "right") if up == "left" else ("right", "left")
        )

    dual = analyze_dual_creativity(
        user_raw,
        ref_raw,
        audio_video_path=audio_path,
        user_offset_sec=user_offset,
        ref_offset_sec=ref_offset,
        user_end_sec=user_end,
        ref_end_sec=ref_end,
        alignment=alignment,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
        baseline=baseline,
        analysis_mode=analysis_mode,
        stream_labels=stream_labels,
        pause_tuning_level=pause_tuning_level,
        motion_segmentation=motion_segmentation,
        motion_scoring=motion_scoring,
    )

    creativity_result: dict[str, Any] = {
        "score": dual.get("score", 0.0),
        "breakdown": dual.get("breakdown") or {},
        "rhythm": dual.get("rhythm"),
        "motion": dual.get("motion"),
    }

    inputs: dict[str, Any] = {
        "user": str(user_p),
        "reference": str(ref_p),
        "media_type": "video",
        "analysis_mode": analysis_mode,
        "pipeline": "motion",
        "motion_segmentation": motion_segmentation,
        "motion_scoring": motion_scoring,
        "user_offset_sec": user_offset,
        "user_end_sec": user_end,
        "ref_offset_sec": ref_offset,
        "ref_end_sec": ref_end,
        "music_align": use_music,
        "alignment": alignment,
        "apply_mirror": apply_mirror,
        "visibility_threshold": visibility_threshold,
        "baseline": baseline,
        "pause_tuning_level": pause_tuning_level,
    }
    if extra_inputs:
        inputs.update(extra_inputs)

    payload: dict[str, Any] = {
        "inputs": inputs,
        "beat_grid": dual.get("beat_grid"),
        "creativity": creativity_result,
        "rhythm": dual.get("rhythm"),
        "motion": dual.get("motion"),
    }
    if music_info is not None:
        payload["music_align"] = music_info

    if save_extractions:
        ensure_output_dirs()
        out_dir = save_dir or _DEFAULT_SAVE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        save_extraction(user_raw, out_dir / "user.creativity.full.json")
        save_extraction(ref_raw, out_dir / "reference.creativity.full.json")

    return payload


def _analyze_segment_mode(
    user_p: Path,
    ref_p: Path,
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    *,
    music_align: bool,
    user_offset_sec: float,
    ref_offset_sec: float,
    auto_detect_start: bool,
    baseline: bool,
    with_accuracy: bool,
    with_llm_adjustment: bool,
    alignment: AlignmentMethod,
    apply_mirror: bool,
    visibility_threshold: float,
    save_extractions: bool,
    save_dir: Path | None,
    num_motion_units: int = 3,
    idle_min_frames: int = 3,
    motion_velocity_threshold: float | None = None,
    min_blend_weight: float = 0.15,
    extra_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_offset, user_end, ref_offset, ref_end, music_info, use_music = _resolve_video_windows(
        user_p,
        ref_p,
        user_raw,
        ref_raw,
        music_align=music_align,
        user_offset_sec=user_offset_sec,
        ref_offset_sec=ref_offset_sec,
        auto_detect_start=auto_detect_start,
    )

    ref_frames = ref_raw.get("frames") or []
    user_frames = user_raw.get("frames") or []
    ref_fps = float(ref_raw.get("fps") or 30.0)

    ref_win_end = ref_end
    if ref_win_end is None and ref_frames:
        ref_win_end = float(max(float(f.get("time_sec", 0.0)) for f in ref_frames))
    user_win_end = user_end
    if user_win_end is None and user_frames:
        user_win_end = float(max(float(f.get("time_sec", 0.0)) for f in user_frames))

    if ref_win_end is None or ref_win_end <= ref_offset:
        raise ValueError("segment 모드: 레퍼런스 비교 구간을 정할 수 없습니다.")

    seg_detect = detect_ref_segments(
        ref_frames,
        window_start_sec=ref_offset,
        window_end_sec=ref_win_end,
        fps=ref_fps,
        idle_min_frames=idle_min_frames,
        num_motion_units=num_motion_units,
        motion_velocity_threshold=motion_velocity_threshold,
    )
    segments = seg_detect.get("segments") or []
    if not segments:
        reason = seg_detect.get("error") or "no_segments"
        raise ValueError(f"segment 모드: 분할된 동작 단위가 없습니다 ({reason}).")

    user_mirrored, user_mirror = prepare_mirrored_frames(user_raw, apply_mirror=apply_mirror)
    ref_mirrored, ref_mirror = prepare_mirrored_frames(ref_raw, apply_mirror=apply_mirror)

    alignment_method: AlignmentMethod = alignment
    segment_rows: list[dict[str, Any]] = []

    for seg in segments:
        r0 = float(seg["start_sec"])
        r1 = float(seg["end_sec"])
        u0, u1 = map_segment_to_user_time(
            r0,
            r1,
            ref_window_start=ref_offset,
            user_window_start=user_offset,
            user_window_end=user_win_end,
        )

        n_k = count_frames_in_time_window(ref_mirrored, r0, r1)
        if n_k < 1:
            segment_rows.append(
                {
                    "index": seg["index"],
                    "ref_window_sec": [r0, r1],
                    "user_window_sec": [u0, u1],
                    "frame_count": 0,
                    "duration_sec": seg["duration_sec"],
                    "skipped": True,
                    "reason": "no_frames_in_window",
                }
            )
            continue

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
            method=alignment_method,
            user_offset_sec=0.0,
            ref_offset_sec=0.0,
        )
        if not pairs:
            segment_rows.append(
                {
                    "index": seg["index"],
                    "ref_window_sec": [r0, r1],
                    "user_window_sec": [u0, u1],
                    "frame_count": n_k,
                    "duration_sec": seg["duration_sec"],
                    "skipped": True,
                    "reason": "no_pairs",
                }
            )
            continue

        dtw_cost = align_meta.get("dtw_mean_cost")
        baseline_pairs = None
        baseline_dtw: float | None = None
        if baseline:
            baseline_pairs, baseline_align = align_extractions(
                ref_ext,
                ref_ext,
                method=alignment_method,
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
        seg_frames_u = user_ext.get("frames") or []
        seg_frames_r = ref_ext.get("frames") or []
        frame_diffs = enrich_frame_diffs_with_times(
            creativity_seg.get("frame_diffs") or [],
            seg_frames_u,
            seg_frames_r,
        )
        creativity_seg["frame_diffs"] = frame_diffs
        peak_windows = extract_peak_divergence_windows(frame_diffs)
        row: dict[str, Any] = {
            "index": seg["index"],
            "ref_window_sec": [round(r0, 4), round(r1, 4)],
            "user_window_sec": [round(u0, 4), round(u1, 4)],
            "frame_count": n_k,
            "duration_sec": seg["duration_sec"],
            "peak_divergence_windows": peak_windows,
            "alignment": align_meta,
            "creativity": creativity_seg,
            "preprocess": {
                "user": user_ext.get("preprocess"),
                "reference": ref_ext.get("preprocess"),
            },
        }
        if with_accuracy:
            row["accuracy"] = score_accuracy(
                pairs,
                dtw_mean_cost=dtw_cost,
                reference_pairs=baseline_pairs,
                reference_dtw_mean_cost=baseline_dtw,
            )
        segment_rows.append(row)

    scored_rows = [r for r in segment_rows if r.get("creativity")]
    if not scored_rows:
        raise ValueError("segment 모드: 채점 가능한 구간이 없습니다.")

    creativity_result = aggregate_segment_creativity_scores(
        scored_rows,
        min_blend_weight=min_blend_weight,
    )
    bd = creativity_result.get("breakdown") or {}
    timing_summary = build_creativity_timing_summary(
        segment_rows,
        analysis_window_reference=(ref_offset, ref_win_end),
        analysis_window_user=(user_offset, user_win_end),
        weighted_mean_score=bd.get("weighted_mean_score"),
    )
    bd["timing"] = timing_summary
    creativity_result["breakdown"] = bd
    if with_llm_adjustment:
        from .llm_creativity import apply_llm_hybrid_to_creativity

        creativity_result = apply_llm_hybrid_to_creativity(creativity_result)

    inputs_seg: dict[str, Any] = {
            "user": str(user_p),
            "reference": str(ref_p),
            "media_type": "video",
            "segment_mode": True,
            "pipeline": "motion_units",
            "segment_method": "motion_idle",
            "num_motion_units": num_motion_units,
            "idle_min_frames": idle_min_frames,
            "motion_velocity_threshold": motion_velocity_threshold,
            "min_blend_weight": min_blend_weight,
            "user_offset_sec": user_offset,
            "user_end_sec": user_end,
            "ref_offset_sec": ref_offset,
            "ref_end_sec": ref_end,
            "music_align": use_music,
            "auto_detect_start": auto_detect_start and not use_music,
            "alignment": alignment_method,
            "apply_mirror": apply_mirror,
            "visibility_threshold": visibility_threshold,
            "baseline": baseline,
            "with_accuracy": with_accuracy,
            "with_llm_adjustment": with_llm_adjustment,
        }
    if extra_inputs:
        inputs_seg.update(extra_inputs)
    payload: dict[str, Any] = {
        "inputs": inputs_seg,
        "segment_detection": seg_detect,
        "segments": segment_rows,
        "timing": timing_summary,
        "creativity": creativity_result,
    }
    if music_info is not None:
        payload["music_align"] = music_info

    if save_extractions:
        ensure_output_dirs()
        out_dir = save_dir or _DEFAULT_SAVE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        save_extraction(user_raw, out_dir / "user.creativity.full.json")
        save_extraction(ref_raw, out_dir / "reference.creativity.full.json")

    return payload
