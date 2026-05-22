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
from .preprocess import preprocess_extraction, resolve_offset_sec

AlignmentMethod = Literal["index", "time", "dtw"]

_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
_DEFAULT_SAVE_DIR = _OUTPUT_ROOT / "extractions"


def ensure_output_dirs() -> None:
    _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    _DEFAULT_SAVE_DIR.mkdir(parents=True, exist_ok=True)


def analyze_media_pair(
    user_path: str | Path,
    reference_path: str | Path,
    *,
    num_frames: int = 50,
    user_offset_sec: float = 0.0,
    ref_offset_sec: float = 0.0,
    auto_detect_start: bool = False,
    music_align: bool = True,
    baseline: bool = True,
    with_accuracy: bool = False,
    alignment: AlignmentMethod = "dtw",
    apply_mirror: bool = True,
    visibility_threshold: float = 0.5,
    save_extractions: bool = False,
    save_dir: Path | None = None,
) -> dict[str, Any]:
    """
    사용자·레퍼런스 미디어 쌍 → 음악 구간·샘플·정렬·3단계 창의성 점수.

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

    effective_num_frames = 1 if user_is_image else num_frames
    if effective_num_frames < 1:
        raise ValueError("num_frames 는 1 이상이어야 합니다.")

    user_raw = extract_from_media(str(user_p))
    ref_raw = extract_from_media(str(ref_p))

    user_offset = 0.0
    ref_offset = 0.0
    user_end: float | None = None
    ref_end: float | None = None
    music_info: dict[str, Any] | None = None
    use_music = False

    if not user_is_image:
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

    user_ext = preprocess_extraction(
        user_raw,
        effective_num_frames,
        offset_sec=user_offset,
        end_sec=user_end,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
    )
    ref_ext = preprocess_extraction(
        ref_raw,
        effective_num_frames,
        offset_sec=ref_offset,
        end_sec=ref_end,
        apply_mirror=apply_mirror,
        visibility_threshold=visibility_threshold,
    )

    if save_extractions:
        ensure_output_dirs()
        out_dir = save_dir or _DEFAULT_SAVE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        save_extraction(user_ext, out_dir / "user.creativity.json")
        save_extraction(ref_ext, out_dir / "reference.creativity.json")

    alignment_method: AlignmentMethod = "index" if user_is_image else alignment
    pairs, align_meta = align_extractions(
        user_ext,
        ref_ext,
        method=alignment_method,
        user_offset_sec=0.0,
        ref_offset_sec=0.0,
    )

    if not pairs:
        raise ValueError("비교할 프레임이 없습니다. 포즈·visibility를 확인하세요.")

    dtw_cost = align_meta.get("dtw_mean_cost")

    baseline_pairs = None
    baseline_dtw: float | None = None
    if baseline and not user_is_image:
        baseline_pairs, baseline_align = align_extractions(
            ref_ext,
            ref_ext,
            method=alignment_method,
            user_offset_sec=0.0,
            ref_offset_sec=0.0,
        )
        baseline_dtw = baseline_align.get("dtw_mean_cost")

    creativity_result = score_creativity(
        pairs,
        dtw_mean_cost=dtw_cost,
        baseline_pairs=baseline_pairs,
        baseline_dtw_mean_cost=baseline_dtw,
    )

    payload: dict[str, Any] = {
        "inputs": {
            "user": str(user_p),
            "reference": str(ref_p),
            "media_type": "image" if user_is_image else "video",
            "num_frames": effective_num_frames,
            "user_offset_sec": user_offset,
            "user_end_sec": user_end,
            "ref_offset_sec": ref_offset,
            "ref_end_sec": ref_end,
            "music_align": use_music,
            "auto_detect_start": auto_detect_start and not user_is_image and not use_music,
            "alignment": alignment_method,
            "apply_mirror": apply_mirror,
            "visibility_threshold": visibility_threshold,
            "baseline": baseline,
            "with_accuracy": with_accuracy,
        },
        "preprocess": {
            "user": user_ext.get("preprocess"),
            "reference": ref_ext.get("preprocess"),
        },
        "alignment": align_meta,
        "creativity": creativity_result,
    }
    if music_info is not None:
        payload["music_align"] = music_info
    if with_accuracy:
        payload["accuracy"] = score_accuracy(
            pairs,
            dtw_mean_cost=dtw_cost,
            reference_pairs=baseline_pairs,
            reference_dtw_mean_cost=baseline_dtw,
        )
    return payload
