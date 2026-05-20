import os

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from domain.domain1.hub.services.analyze_service import run_analyze
from domain.domain1.hub.services.comparison_service import compute_comparison
from domain.domain1.hub.services.extraction_pipeline import (
    run_extraction_and_save,
    save_upload_to_temp,
)
from domain.domain1.hub.services.storage_paths import (
    load_extraction_json,
    validate_filename,
    video_path,
)
from domain.domain1.models.transfer.compare_request import CompareRequest

router = APIRouter(prefix="/video", tags=["video"])


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
    "/analyze",
    summary="사용자 영상 업로드 → 추출 → 레퍼런스 JSON과 비교·채점",
    description=(
        "사용자 동영상 1개만 업로드합니다. "
        "reference_json은 video_json/에 미리 저장된 전문가 추출 JSON 파일명입니다. "
        "응답: user 추출 메타 + scores(accuracy, rom, total_score) + alignment."
    ),
)
async def analyze_video(
    user_video: UploadFile = File(..., description="사용자 댄스 영상"),
    reference_json: str = Form(
        ...,
        description="video_json/ 아래 레퍼런스(전문가) JSON 파일명",
    ),
    alignment_method: str = Form("time"),
    user_offset_sec: float = Form(0.0),
    ref_offset_sec: float = Form(0.0),
    auto_detect_start: bool = Form(False),
    detail_level: str = Form("summary"),
    scoring_mode: str = Form("dance"),
    enable_rom: bool = Form(True),
):
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(user_video)
        result = run_analyze(
            user_video_path=tmp_path,
            reference_json_filename=reference_json,
            alignment_method=alignment_method,
            user_offset_sec=user_offset_sec,
            ref_offset_sec=ref_offset_sec,
            auto_detect_start=auto_detect_start,
            detail_level=detail_level,  # type: ignore[arg-type]
            scoring_mode=scoring_mode,  # type: ignore[arg-type]
            enable_rom=enable_rom,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return JSONResponse(content=result)


@router.post(
    "/compare",
    summary="저장된 추출 JSON 2개로 동작 비교·채점",
    description=(
        "video_json/에 저장된 사용자·전문가 추출 JSON 파일명을 지정하면 "
        "프레임 정렬(time|dtw) 후 Accuracy·ROM 점수를 반환합니다."
    ),
)
async def compare_videos(body: CompareRequest):
    try:
        result = compute_comparison(
            user_json_filename=body.user_json,
            reference_json_filename=body.reference_json,
            alignment_method=body.alignment_method,
            user_offset_sec=body.user_offset_sec,
            ref_offset_sec=body.ref_offset_sec,
            auto_detect_start=body.auto_detect_start,
            detail_level=body.detail_level,
            scoring_mode=body.scoring_mode,
            enable_rom=body.enable_rom,
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
        "분석 오버레이 MP4를 video_data/에 저장."
    ),
)
async def extract_video(file: UploadFile = File(...)):
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(file)
        result = run_extraction_and_save(tmp_path)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
