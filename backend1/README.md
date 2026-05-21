# backend1 — FOM 통합 API

[metrics/docs/ARCHITECTURE.md](metrics/docs/ARCHITECTURE.md) 기준 **유일한 HTTP 진입점**입니다.  
오케스트레이터·추출 조율 정리: [metrics/docs/ORCHESTRATOR.md](metrics/docs/ORCHESTRATOR.md).

## 실행

```bash
cd backend1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 엔드포인트

| 메서드 | URL | 설명 |
|--------|-----|------|
| `POST` | `/video/extract` | 영상 **파일** 또는 **video_url** → 추출 JSON 저장 |
| `POST` | `/video/analyze` | 유저 영상 → **추출 병렬** + **6 metric 채점** (오케스트레이터) |
| `POST` | `/video/analyze/json` | 저장 JSON 2개 → **6 metric 병렬** 채점 (`metrics` 필드) |
| `POST` | `/rhythm/*` | rhythm 전용 (기존 `/video` 와 분리) |
| `POST` | `/isolation/*` | isolation 전용 |
| `POST` | `/power/*` | power 전용 |
| `POST` | `/video/compare` | 저장 JSON 2개 비교 (개발·디버그) |
| `GET` | `/video/json/{filename}` | 추출 JSON 다운로드 |
| `GET` | `/video/data/{filename}` | annotated MP4 |
| `GET` | `/health` | 헬스체크 |

## 구현 위치

- HTTP: `backend1/routers/video.py`
- 추출 병렬: `backend1/services/extract_coordinator.py`
- 채점 병렬: `backend1/services/orchestrator.py`
- ROM 로직: `metrics/rom/domain/domain1/`
- ROM 기술 정리: `metrics/rom/domain/domain1/docs/ROM_IMPLEMENTATION_TECH.md`
- `main.py` 시작부: `metrics/rom` → `sys.path` ( `domain.domain1` import용 )

`metrics/rom/main.py`, `metrics/rom/routers/` 는 사용하지 않습니다.

## 클라이언트 흐름 (권장)

1. 레퍼런스: `POST /video/extract` 로 JSON 1회 생성
2. 유저: `POST /video/analyze` — `user_video` **또는** `video_url` + `reference_json`
3. (선택) 재채점만: `POST /video/analyze/json`
