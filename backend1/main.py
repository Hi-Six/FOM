from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.video import router as video_router
from metrics.rhythm.routers.video import router as rhythm_router

app = FastAPI(
    title="FOM — Dance Analysis API",
    description="6차원 채점 통합 API (`POST /video/analyze`)",
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
    return {"status": "ok"}
