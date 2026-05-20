"""사용자 영상 추출 후 리듬 채점."""

import os
import tempfile
from typing import Any, Dict

from fastapi import UploadFile

from .extraction_service import extract_rhythm_data
from .scoring.rhythm_scorer import score_rhythm_from_extraction
from .storage_paths import (
    build_json_meta,
    ensure_storage_dirs,
    make_extraction_basename,
    save_extraction_json,
)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_MB = 500


def validate_video_extension(filename: str | None) -> str:
    ext = os.path.splitext(filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"지원하지 않는 형식입니다. 허용: {sorted(ALLOWED_EXTENSIONS)}")
    return ext


async def save_upload_to_temp(file: UploadFile) -> tuple[str, str]:
    """업로드 파일을 임시 경로에 저장. (tmp_path, ext) 반환."""
    ext = validate_video_extension(file.filename)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"파일 크기가 {MAX_FILE_SIZE_MB}MB를 초과합니다.")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        return tmp.name, ext


def run_extraction_and_save(video_path: str) -> Dict[str, Any]:
    """영상 경로 → 추출 후 JSON 저장. 추출 메타 반환."""
    result = extract_rhythm_data(video_path)
    ensure_storage_dirs()
    base = make_extraction_basename()
    json_name = f"{base}.json"
    save_extraction_json(result, json_name)
    result["extraction_id"] = base
    result["extraction_json"] = build_json_meta(json_name)
    result["json_filename"] = json_name
    return result


def run_analyze(user_video_path: str) -> Dict[str, Any]:
    """영상 경로 → 추출 → 리듬 채점 → 결과 반환."""
    extraction = run_extraction_and_save(user_video_path)
    score_result = score_rhythm_from_extraction(extraction)
    return {
        "extraction_id": extraction["extraction_id"],
        "extraction_json": extraction["extraction_json"],
        "fps": extraction.get("fps"),
        "total_frames": extraction.get("total_frames"),
        "scores": {"rhythm": score_result},
    }
