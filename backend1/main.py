"""FOM 통합 API — uvicorn main:app (ROM path는 이 파일에서만 설정)."""

import sys
from pathlib import Path

# routers/video → domain.domain1 import 전에 metrics/rom 을 sys.path에 추가
_ROM_ROOT = Path(__file__).resolve().parent / "metrics" / "rom"
_rom_root_str = str(_ROM_ROOT)
if _rom_root_str not in sys.path:
    sys.path.append(_rom_root_str)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.video import router as video_router
from metrics.rhythm.routers.video import router as rhythm_router

app = FastAPI(
    title="FOM — Dance Analysis API",
    description=(
        "통합 API (backend1). "
        "POST /video/analyze — 유저 영상 업로드 + 레퍼런스 JSON 채점. "
        "POST /video/analyze/json — 저장 JSON 2개 채점. "
        "POST /video/extract — ROM domain1 추출."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rhythm_router)   # rhythm: /video/analyze, /video/extract, /video/visualize 등
app.include_router(video_router)    # 통합 오케스트레이터 stub (501)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "entry": "backend1/main.py",
        "rom_domain": "metrics/rom/domain/domain1",
    }
