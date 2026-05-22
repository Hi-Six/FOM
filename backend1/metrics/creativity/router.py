"""
Creativity 전용 HTTP API — 통합 POST /video/analyze 와 분리.

전체 파이프라인: 음악 구간 정렬 → 균등 샘플(기본 50) → DTW → 3단계 창의성 점수.
"""

from __future__ import annotations

import os
import tempfile
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from metrics.creativity.service import analyze_media_pair

router = APIRouter(prefix="/creativity", tags=["creativity"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"}
MAX_MB = 500


def _ext(filename: str | None) -> str:
    return os.path.splitext(filename or "")[-1].lower()


@router.get(
    "/ready",
    summary="creativity API 준비 상태",
)
def creativity_ready() -> dict:
    return {
        "ready": True,
        "metric": "creativity",
        "pipeline": "music_align → sample → align(dtw) → score_creativity",
        "analyze_endpoint": "POST /creativity/analyze",
    }


@router.post(
    "/analyze",
    summary="사용자·레퍼런스 영상/이미지 쌍 → 창의성 점수 (전체 파이프라인)",
    description=(
        "동일 BGM 전제 크로마 음악 구간 정렬(기본 on), 구간 내 균등 샘플(기본 50프레임), "
        "DTW 정렬, ref vs ref 기준선 보정(기본 on). "
        "6 metric 통합 POST /video/analyze 와 별도 — CLI와 동일 파이프라인입니다."
    ),
)
async def analyze_creativity(
    user_video: UploadFile = File(..., description="사용자 영상 또는 이미지"),
    reference_video: UploadFile = File(..., description="레퍼런스 영상 또는 이미지"),
    num_frames: int = Form(
        50,
        ge=1,
        le=200,
        description="음악 구간(또는 offset 이후) 균등 샘플 프레임 수",
    ),
    user_offset_sec: float = Form(
        0.0,
        ge=0.0,
        description="사용자 샘플 시작(초). 0이 아니면 음악 정렬 스킵",
    ),
    ref_offset_sec: float = Form(
        0.0,
        ge=0.0,
        description="레퍼런스 샘플 시작(초). 0이 아니면 음악 정렬 스킵",
    ),
    auto_detect_start: bool = Form(
        False,
        description="포즈 움직임으로 춤 시작 추정 (음악 정렬과 동시 사용 안 함)",
    ),
    music_align: bool = Form(
        True,
        description="동일 BGM 크로마 구간 [시작,끝] 정렬 후 샘플",
    ),
    baseline: bool = Form(
        True,
        description="ref vs ref 기준선 보정",
    ),
    with_accuracy: bool = Form(
        False,
        description="동일 파이프라인 정확도 점수 함께 반환",
    ),
    alignment: Literal["index", "time", "dtw"] = Form(
        "dtw",
        description="프레임 정렬 (이미지 쌍은 index 고정)",
    ),
    apply_mirror: bool = Form(True, description="미러 감지 시 좌우 관절 스왑"),
    visibility_threshold: float = Form(
        0.5,
        ge=0.0,
        le=1.0,
        description="핵심 관절 visibility 최소값",
    ),
    save_extractions: bool = Form(
        False,
        description="metrics/creativity/output/extractions/ 에 추출 JSON 저장",
    ),
):
    user_ext = _ext(user_video.filename)
    ref_ext = _ext(reference_video.filename)
    for label, ext in (("사용자", user_ext), ("레퍼런스", ref_ext)):
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"{label} 지원하지 않는 형식: {ext}. 허용: {sorted(ALLOWED_EXTENSIONS)}",
            )

    user_content = await user_video.read()
    ref_content = await reference_video.read()
    for label, content in (("사용자", user_content), ("레퍼런스", ref_content)):
        if len(content) > MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{label} 파일 크기 {MAX_MB}MB 초과")

    user_tmp: str | None = None
    ref_tmp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=user_ext, delete=False) as u:
            user_tmp = u.name
            u.write(user_content)
        with tempfile.NamedTemporaryFile(suffix=ref_ext, delete=False) as r:
            ref_tmp = r.name
            r.write(ref_content)

        result = analyze_media_pair(
            user_tmp,
            ref_tmp,
            num_frames=num_frames,
            user_offset_sec=user_offset_sec,
            ref_offset_sec=ref_offset_sec,
            auto_detect_start=auto_detect_start,
            music_align=music_align,
            baseline=baseline,
            with_accuracy=with_accuracy,
            alignment=alignment,
            apply_mirror=apply_mirror,
            visibility_threshold=visibility_threshold,
            save_extractions=save_extractions,
        )
        result["meta"] = {
            "user_filename": user_video.filename,
            "reference_filename": reference_video.filename,
            "endpoint": "POST /creativity/analyze",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"creativity 분석 오류: {e}") from e
    finally:
        for p in (user_tmp, ref_tmp):
            if p and os.path.exists(p):
                os.remove(p)

    return JSONResponse(content=result)
