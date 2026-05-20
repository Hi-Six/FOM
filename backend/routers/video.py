import os
import tempfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from domain.domain1.hub.services.extraction_service import extract_dance_data
from domain.domain1.hub.services.video_visualizer import (
    VIDEO_DATA_DIR,
    build_annotated_video_meta,
    ensure_video_data_dir,
    render_annotated_video,
)

router = APIRouter(prefix="/video", tags=["video"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_MB = 500


@router.get(
    "/data/{filename}",
    summary="분석 오버레이 영상 다운로드",
    response_class=FileResponse,
)
def get_annotated_video(filename: str):
    """video_data에 저장된 annotated 영상 파일 반환."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = VIDEO_DATA_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
    )


@router.post(
    "/extract",
    summary="영상에서 댄스 랜드마크 데이터 추출 + 분석 영상 생성",
    description=(
        "동영상 파일을 업로드하면 프레임별 landmarks, normalized_landmarks, "
        "bone_vectors, joint_angles JSON과 함께 분석 오버레이가 적용된 MP4를 "
        "domain1/video_data에 저장하고 다운로드 URL을 반환합니다."
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
        ensure_video_data_dir()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_name = f"{stamp}_{uuid.uuid4().hex[:8]}_annotated.mp4"
        render_annotated_video(tmp_path, result, out_name)
        result["annotated_video"] = build_annotated_video_meta(out_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return JSONResponse(content=result)
