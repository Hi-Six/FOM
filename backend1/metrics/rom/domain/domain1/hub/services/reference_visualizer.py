"""레퍼런스 추출 JSON + 전문가 MP4 → 캐시된 annotated MP4."""

from __future__ import annotations

from pathlib import Path

from .storage_paths import (
    EXTRACTION_SCHEMA_ROM,
    build_annotated_video_meta,
    load_extraction_json,
    video_path,
)
from .video_visualizer import (
    MAX_ANNOTATED_CACHE_BYTES,
    ensure_video_data_dir,
    render_annotated_video,
)


def _cache_filename(reference_json_filename: str) -> str:
    stem = Path(reference_json_filename).stem
    return f"ref_{stem}_annotated.mp4"


def ensure_reference_annotated_video(
    reference_json_filename: str,
    reference_video_filename: str,
    *,
    force_regenerate: bool = False,
) -> dict | None:
    """
    reference_json(full_v1) + video_data/ MP4 로 전문가 오버레이 MP4 생성·캐시.

    Returns annotated_video meta dict or None (rom_v1·파일 없음·렌더 실패).
    """
    ref_data = load_extraction_json(reference_json_filename)
    if ref_data.get("schema") == EXTRACTION_SCHEMA_ROM:
        return None

    src = video_path(reference_video_filename)
    if not src.is_file():
        return None

    ensure_video_data_dir()
    out_name = _cache_filename(reference_json_filename)
    out_path = video_path(out_name)

    if out_path.is_file():
        size = out_path.stat().st_size
        if size > MAX_ANNOTATED_CACHE_BYTES:
            force_regenerate = True
        elif not force_regenerate and size > 10_000:
            return build_annotated_video_meta(out_name)

    try:
        render_annotated_video(str(src), ref_data, out_name)
    except (ValueError, OSError):
        if out_path.is_file() and out_path.stat().st_size > 10_000:
            return build_annotated_video_meta(out_name)
        return None

    if not out_path.is_file() or out_path.stat().st_size < 1000:
        return None
    return build_annotated_video_meta(out_name)
