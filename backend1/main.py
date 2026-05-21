from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rom_path import ensure_rom_domain_on_path
from routers.video import router as video_router

ensure_rom_domain_on_path()

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

app.include_router(video_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "entry": "backend1/main.py",
        "rom_domain": "metrics/rom/domain/domain1",
    }
