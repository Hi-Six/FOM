"""
통합 /video API — HTTP 진입점.
구현: metrics/rom/domain/domain1 (ROM metric, ARCHITECTURE.md §1).
"""

import os
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from rom_path import ensure_rom_domain_on_path

ensure_rom_domain_on_path()

from domain.domain1.hub.services.analyze_service import run_analyze
from domain.domain1.hub.services.comparison_service import compute_comparison
from domain.domain1.hub.services.extraction_pipeline import run_extraction_and_save
from domain.domain1.hub.services.video_input import acquire_video_to_temp
from domain.domain1.hub.services.storage_paths import (
    load_extraction_json,
    validate_filename,
    video_path,
)
from domain.domain1.models.transfer.compare_request import CompareRequest

router = APIRouter(prefix="/video", tags=["video"])


class AnalyzeJsonRequest(BaseModel):
    """ARCHITECTURE.md §2.1 — 저장된 추출 JSON 2개로 채점 (영상 업로드 없음)."""

    user_json: str = Field(..., description="video_json/ 사용자 추출 JSON 파일명")
    reference_json: str = Field(..., description="video_json/ 레퍼런스 추출 JSON 파일명")
    alignment_method: Literal["time", "dtw"] = Field("time")
    user_offset_sec: float = Field(0.0, ge=0.0)
    ref_offset_sec: float = Field(0.0, ge=0.0)
    auto_detect_start: bool = Field(False)
    detail_level: Literal["summary", "full"] = Field("summary")
    scoring_mode: Literal["linear", "dance"] = Field("dance")
    enable_accuracy: bool = Field(
        False,
        description="Accuracy 채점 (full_v1 JSON 필요). ROM만 쓸 때 False",
    )
    enable_rom: bool = Field(True, description="ROM 채점 (domain1)")


@router.post(
    "/analyze",
    summary="유저 영상 업로드 + 레퍼런스 JSON 채점 (권장)",
    description=(
        "사용자 동영상: multipart file 또는 video_url(HTTP(S) 직링크) 중 하나. "
        "reference_json은 video_json/에 미리 저장된 전문가 추출 JSON 파일명입니다. "
        "서버가 사용자 영상을 추출(기본 rom_v1·15fps)한 뒤 레퍼런스와 비교합니다. "
        "기본: ROM 전용(enable_accuracy=false). "
        "저장 JSON만으로 채점할 때는 POST /video/analyze/json."
    ),
)
async def analyze_video(
    user_video: Optional[UploadFile] = File(
        None, description="사용자 댄스 영상 (video_url과 택1)"
    ),
    video_url: Optional[str] = Form(
        None,
        description="사용자 영상 HTTP(S) URL (user_video와 택1, mp4/mov 등 직링크)",
    ),
    reference_json: str = Form(
        ...,
        description="video_json/ 레퍼런스 추출 JSON 파일명",
    ),
    alignment_method: Literal["time", "dtw"] = Form("time"),
    user_offset_sec: float = Form(0.0),
    ref_offset_sec: float = Form(0.0),
    auto_detect_start: bool = Form(False),
    detail_level: Literal["summary", "full"] = Form("summary"),
    scoring_mode: Literal["linear", "dance"] = Form("dance"),
    enable_accuracy: bool = Form(False),
    enable_rom: bool = Form(True),
    extraction_mode: Literal["rom", "full"] = Form(
        "rom",
        description="사용자 영상 추출: rom=경량, full=Accuracy용",
    ),
    target_fps: Optional[float] = Form(
        15.0,
        description="ROM 샘플링 목표 fps. 0 이하면 전체 프레임",
    ),
    frame_stride: Optional[int] = Form(
        None,
        description="지정 시 target_fps보다 우선",
    ),
):
    tmp_path = None
    try:
        tmp_path, _ = await acquire_video_to_temp(
            upload=user_video, video_url=video_url
        )
        effective_target = target_fps if target_fps and target_fps > 0 else None
        result = run_analyze(
            user_video_path=tmp_path,
            reference_json_filename=reference_json,
            alignment_method=alignment_method,
            user_offset_sec=user_offset_sec,
            ref_offset_sec=ref_offset_sec,
            auto_detect_start=auto_detect_start,
            detail_level=detail_level,
            scoring_mode=scoring_mode,
            enable_accuracy=enable_accuracy,
            enable_rom=enable_rom,
            extraction_mode=extraction_mode,
            target_fps=effective_target,
            frame_stride=frame_stride,
        )
        return JSONResponse(content=result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=422, detail=f"영상 URL 다운로드 오류: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"채점 중 오류: {e}") from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post(
    "/analyze/json",
    summary="저장 JSON 2개로 채점 (ARCHITECTURE §2.1)",
    description=(
        "이미 추출·저장된 user_json / reference_json으로만 채점합니다. "
        "유저 영상 업로드는 POST /video/analyze 를 사용하세요."
    ),
)
async def analyze_video_from_json(body: AnalyzeJsonRequest) -> dict:
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
            enable_accuracy=body.enable_accuracy,
            enable_rom=body.enable_rom,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"채점 중 오류: {e}") from e

    return {
        "alignment": result.get("alignment"),
        "scores": result.get("scores"),
        "meta": result.get("meta"),
        "user_json": result.get("user_json", body.user_json),
        "reference_json": result.get("reference_json", body.reference_json),
    }


@router.post(
    "/extract",
    summary="영상 추출 (ROM domain1 위임)",
    description=(
        "동영상 file 또는 video_url(HTTP(S)) → 추출 JSON을 video_json/에 저장. "
        "기본 extraction_mode=rom (15fps 샘플링, annotated MP4 생략). "
        "Accuracy용은 extraction_mode=full."
    ),
)
async def extract_video(
    file: Optional[UploadFile] = File(None, description="업로드 영상 (video_url과 택1)"),
    video_url: Optional[str] = Form(
        None,
        description="영상 HTTP(S) URL (file과 택1)",
    ),
    extraction_mode: Literal["rom", "full"] = Form(
        "rom",
        description="rom=경량 joint_angles, full=Accuracy용 전체 필드",
    ),
    target_fps: Optional[float] = Form(
        15.0,
        description="MediaPipe 샘플링 목표 fps (rom 기본 15). 0 이하면 전체 프레임",
    ),
    frame_stride: Optional[int] = Form(
        None,
        description="지정 시 target_fps보다 우선 (N프레임마다 1회 처리)",
    ),
    include_annotated_video: Optional[bool] = Form(
        None,
        description="None=rom이면 생략, full이면 생성. True/False로 강제",
    ),
):
    tmp_path = None
    try:
        tmp_path, _ = await acquire_video_to_temp(upload=file, video_url=video_url)
        effective_target = target_fps if target_fps and target_fps > 0 else None
        result = run_extraction_and_save(
            tmp_path,
            mode=extraction_mode,
            target_fps=effective_target,
            frame_stride=frame_stride,
            include_annotated_video=include_annotated_video,
        )
        return JSONResponse(content=result)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=422, detail=f"영상 URL 다운로드 오류: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추출 중 오류: {e}") from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post(
    "/compare",
    summary="저장 JSON 2개 비교·채점 (ROM domain1)",
    description="video_json/ 파일명 2개. ROM 기본: enable_accuracy=false.",
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
            enable_accuracy=body.enable_accuracy,
            enable_rom=body.enable_rom,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"비교 중 오류: {e}") from e
    return JSONResponse(content=result)


@router.get(
    "/data/{filename}",
    summary="분석 오버레이 영상 다운로드",
    response_class=FileResponse,
)
def get_annotated_video(filename: str):
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
    try:
        data = load_extraction_json(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return JSONResponse(content=data)
