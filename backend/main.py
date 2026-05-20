from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.video import router as video_router

app = FastAPI(
    title="Dance AI — Video Extraction API",
    description="동영상 업로드 → MediaPipe 3D 랜드마크 추출 → 스무딩 → 정규화 → JSON 반환",
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
