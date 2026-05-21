from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from metrics.rhythm.routers.video import router as video_router

app = FastAPI(
    title="FOM — Rhythm Scoring API",
    description="사용자 댄스 영상 → 리듬 규칙성 채점",
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
def health():
    return {"status": "ok"}
