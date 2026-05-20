from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/video", tags=["video"])


class AnalyzeRequest(BaseModel):
    user_json: str = Field(..., description="사용자 추출 JSON 파일명")
    reference_json: str = Field(..., description="레퍼런스 추출 JSON 파일명")
    alignment_method: Literal["time"] = Field(
        default="time",
        description="프레임 정렬 방식",
    )


@router.post(
    "/analyze",
    summary="6차원 채점 (통합)",
    description=(
        "저장된 사용자·레퍼런스 추출 JSON으로 accuracy, creativity, isolation, "
        "power, rhythm, rom 6개 metric을 병렬 채점합니다."
    ),
)
async def analyze_video(body: AnalyzeRequest) -> dict:
    """
    analyze 오케스트레이터(JSON 로드·정렬·6 metric 병렬·병합)는 별도 모듈에서 연결 예정.
    """
    raise HTTPException(
        status_code=501,
        detail="analyze 오케스트레이터가 아직 연결되지 않았습니다.",
    )
