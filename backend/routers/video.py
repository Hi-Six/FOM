import os
import tempfile

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from domain.domain1.hub.services.extraction_service import extract_dance_data
from domain.domain1.hub.services.comparison_service import compute_comparison
from domain.domain1.hub.services.storage_paths import (
    build_annotated_video_meta,
    build_json_meta,
    ensure_storage_dirs,
    load_extraction_json,
    make_extraction_basename,
    save_extraction_json,
    validate_filename,
    video_path,
)
from domain.domain1.hub.services.video_visualizer import render_annotated_video
from domain.domain1.models.transfer.compare_request import CompareRequest

router = APIRouter(prefix="/video", tags=["video"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_MB = 500


@router.get(
    "/data/{filename}",
    summary="분석 오버레이 영상 다운로드",
    response_class=FileResponse,
)
def get_annotated_video(filename: str):
    """video_data에 저장된 annotated MP4 반환."""
    try:
        validate_filename(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    path = video_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.get(
    "/json/{filename}",
    summary="저장된 추출 JSON 다운로드",
)
def get_extraction_json(filename: str):
    """video_data/video_json에 저장된 추출 JSON 반환."""
    try:
        data = load_extraction_json(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return JSONResponse(content=data)


@router.post(
    "/compare",
    summary="저장된 추출 JSON 2개로 동작 비교·채점",
    description=(
        "video_json/에 저장된 사용자·전문가 추출 JSON 파일명을 지정하면 "
        "프레임 정렬(time) 후 joint_angles·bone_vectors 기반 Accuracy 점수를 반환합니다."
    ),
)
async def compare_videos(body: CompareRequest):
    try:
        result = compute_comparison(
            user_json_filename=body.user_json,
            reference_json_filename=body.reference_json,
            alignment_method=body.alignment_method,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"비교 중 오류: {e}")
    return JSONResponse(content=result)


@router.post(
    "/extract",
    summary="영상에서 댄스 랜드마크 데이터 추출 + 분석 영상·JSON 저장",
    description=(
        "동영상 업로드 → 추출 JSON을 video_data/video_json/에 저장, "
        "분석 오버레이 MP4를 video_data/에 저장. "
        "비교 시 extraction_json.filename을 /video/compare에 전달."
    ),
)
async def extract_video(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"지원하지 않는 형식입니다. 허용: {ALLOWED_EXTENSIONS}",
        )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
        content = await file.read()

        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"파일 크기가 {MAX_FILE_SIZE_MB}MB를 초과합니다.",
            )
        tmp.write(content)

    try:
        result = extract_dance_data(tmp_path)
        ensure_storage_dirs()
        base = make_extraction_basename()
        json_name = f"{base}.json"
        mp4_name = f"{base}_annotated.mp4"

        save_extraction_json(result, json_name)
        render_annotated_video(tmp_path, result, mp4_name)

        result["extraction_id"] = base
        result["extraction_json"] = build_json_meta(json_name)
        result["annotated_video"] = build_annotated_video_meta(mp4_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return JSONResponse(content=result)
