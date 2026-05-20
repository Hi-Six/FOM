from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    user_json: str = Field(..., description="video_json/ 아래 사용자 추출 JSON 파일명")
    reference_json: str = Field(..., description="video_json/ 아래 전문가 추출 JSON 파일명")
    alignment_method: str = Field(
        default="time",
        description="프레임 정렬: time (현재 지원)",
    )
