from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.video import router as video_router
from metrics.power.routers.video import router as power_router

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

app.include_router(video_router)
app.include_router(power_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
