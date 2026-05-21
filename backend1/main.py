from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.video import router as video_router
from metrics.isolation.router import router as isolation_router

app = FastAPI(
    title="FOM — Dance Analysis API",
    description="6차원 통합 `/video/analyze` + isolation 전용 `/isolation/analyze`",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video_router)
app.include_router(isolation_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
