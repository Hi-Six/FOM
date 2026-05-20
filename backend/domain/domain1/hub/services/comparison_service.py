"""저장된 추출 JSON 2개를 로드해 비교·채점."""

from typing import Any, Dict, List

from .scoring.accuracy_scorer import score_accuracy, score_to_grade
from .scoring.alignment import align_by_time
from .storage_paths import load_extraction_json

SUPPORTED_ALIGNMENT = frozenset({"time"})


def _validate_extraction(data: Dict[str, Any], label: str) -> None:
    if "frames" not in data or not isinstance(data["frames"], list):
        raise ValueError(f"{label}: 유효하지 않은 추출 JSON (frames 없음)")
    if not data["frames"]:
        raise ValueError(f"{label}: 프레임 데이터가 비어 있습니다.")


def compute_comparison(
    user_json_filename: str,
    reference_json_filename: str,
    alignment_method: str = "time",
) -> Dict[str, Any]:
    """
    video_json에 저장된 두 파일을 로드해 Accuracy 등 비교 결과 반환.
    """
    if alignment_method not in SUPPORTED_ALIGNMENT:
        raise ValueError(
            f"지원하지 않는 정렬 방식: {alignment_method}. "
            f"허용: {sorted(SUPPORTED_ALIGNMENT)}"
        )

    user_data = load_extraction_json(user_json_filename)
    ref_data = load_extraction_json(reference_json_filename)
    _validate_extraction(user_data, "user_json")
    _validate_extraction(ref_data, "reference_json")

    user_frames: List[Dict[str, Any]] = user_data["frames"]
    ref_frames: List[Dict[str, Any]] = ref_data["frames"]

    ratio = len(user_frames) / max(len(ref_frames), 1)
    if ratio > 10 or ratio < 0.1:
        raise ValueError(
            "두 영상의 길이(프레임 수) 차이가 너무 큽니다. "
            f"user={len(user_frames)}, ref={len(ref_frames)}"
        )

    aligned_pairs = align_by_time(user_frames, ref_frames)
    accuracy = score_accuracy(aligned_pairs)

    aligned_summary = [
        {"user_frame": p["user_frame"], "ref_frame": p["ref_frame"]}
        for p in aligned_pairs
    ]

    total_score = accuracy["score"]
    return {
        "user_json": user_json_filename,
        "reference_json": reference_json_filename,
        "alignment": {
            "method": alignment_method,
            "pair_count": len(aligned_pairs),
            "aligned_pairs": aligned_summary,
        },
        "scores": {
            "accuracy": accuracy,
            "total_score": total_score,
            "grade": score_to_grade(total_score),
        },
        "meta": {
            "user_fps": user_data.get("fps"),
            "user_total_frames": user_data.get("total_frames"),
            "reference_fps": ref_data.get("fps"),
            "reference_total_frames": ref_data.get("total_frames"),
        },
    }
