import os
import tempfile
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from domain.domain1.hub.services.extraction_service import extract_dance_data

router = APIRouter(prefix="/video", tags=["video"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_MB = 500


@router.post(
    "/extract",
    summary="영상에서 댄스 랜드마크 데이터 추출",
    description=(
        "동영상 파일을 업로드하면 fps, total_frames와 "
        "프레임별 33개 랜드마크(원본 + Mid-Hip 정규화) JSON을 반환합니다."
    ),
)
async def extract_video(file: UploadFile = File(...)):
    # 확장자 검사
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"지원하지 않는 형식입니다. 허용: {ALLOWED_EXTENSIONS}",
        )

    # 임시 파일에 저장 후 파이프라인 실행
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
        content = await file.read()

        # 파일 크기 제한
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"파일 크기가 {MAX_FILE_SIZE_MB}MB를 초과합니다.",
            )
        tmp.write(content)

    try:
        result = extract_dance_data(tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {e}")
    finally:
        os.remove(tmp_path)

    return JSONResponse(content=result)
