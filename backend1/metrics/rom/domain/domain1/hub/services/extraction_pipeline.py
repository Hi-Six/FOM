"""영상 파일 → 추출·저장 공통 파이프라인."""

import os
import tempfile
from typing import Any, Dict, Tuple

from fastapi import UploadFile

from .extraction_service import extract_dance_data
from .storage_paths import (
    build_annotated_video_meta,
    build_json_meta,
    ensure_storage_dirs,
    json_path,
    make_extraction_basename,
    save_extraction_json,
)
from .video_visualizer import render_annotated_video

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_MB = 500


def validate_video_extension(filename: str | None) -> str:
    ext = os.path.splitext(filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"지원하지 않는 형식입니다. 허용: {sorted(ALLOWED_EXTENSIONS)}")
    return ext


async def save_upload_to_temp(file: UploadFile) -> Tuple[str, str]:
    """업로드 파일을 임시 경로에 저장. (tmp_path, ext) 반환."""
    ext = validate_video_extension(file.filename)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"파일 크기가 {MAX_FILE_SIZE_MB}MB를 초과합니다.")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(content)
    return tmp_path, ext


def run_extraction_and_save(video_path: str) -> Dict[str, Any]:
    """
    로컬 영상 경로에서 추출 후 JSON·annotated MP4 저장.
    반환: 추출 결과 dict + extraction_id/json/annotated 메타 + json_filename(내부용).
    """
    result = extract_dance_data(video_path)
    ensure_storage_dirs()
    base = make_extraction_basename()
    json_name = f"{base}.json"
    mp4_name = f"{base}_annotated.mp4"

    save_extraction_json(result, json_name)
    render_annotated_video(video_path, result, mp4_name)

    result["extraction_id"] = base
    result["extraction_json"] = build_json_meta(json_name)
    result["annotated_video"] = build_annotated_video_meta(mp4_name)
    result["json_filename"] = json_name
    return result


def build_reference_meta(reference_json_filename: str) -> Dict[str, Any]:
    """저장된 레퍼런스 JSON 메타 (파일 존재 검증)."""
    path = json_path(reference_json_filename)
    if not path.is_file():
        raise FileNotFoundError(
            f"레퍼런스 추출 JSON을 찾을 수 없습니다: {reference_json_filename}"
        )
    return {
        "extraction_json": build_json_meta(reference_json_filename),
    }
