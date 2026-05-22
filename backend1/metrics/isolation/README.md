# Isolation metric (로컬 + API)

## 팀 MediaPipe (병합 기준)

- **Tasks API** + `mediapipe>=0.10.31` (`mediapipe_pose_tasks.py`)
- **0.10.30은 Windows/Python 3.12에서 사용 불가** (`function 'free' not found`) → **0.10.31 이상**

## Git에 올리지 않는 것

| 항목 | 위치 | 준비 방법 |
|------|------|-----------|
| YOLO 가중치 | `data/models/yolo11n.pt` | `track` / `extract` 첫 실행 시 자동 다운로드 |
| MediaPipe Heavy | `data/models/pose_landmarker_heavy.task` | `extract` 첫 실행 시 자동 다운로드 (Tasks API) |
| 기준 영상 | `data/raw/ref.mp4` | `cli download` |
| 추출·트랙 JSON | `data/artifacts/*.json` | `cli track` → `cli extract` |

저장소에는 `.gitkeep`·`.gitignore`만 포함됩니다. 클론 후 아래 **첫 설정**을 한 번 실행하세요.

## 첫 설정 (1회)

```powershell
cd backend1
pip install -r requirements.txt
python -m metrics.isolation.cli download
python -m metrics.isolation.cli extract   # → data/artifacts/ref.json (API 필수)
```

**solutions API로 만든 `ref.json`은 Tasks 전환 후 반드시 `extract`로 다시 생성하세요.**

기존에 `backend1/yolo11n.pt`만 있다면 `data/models/`로 옮기거나 삭제 후 재실행해도 됩니다.

## CLI

```powershell
cd backend1
python -m metrics.isolation.cli extract   # ref.json

# 사용자 영상 → 터미널에 점수 JSON
python -m metrics.isolation.cli run --user-video metrics/isolation/data/raw/user.mp4 --json

# ref/user JSON 만 있을 때 (extract 생략)
python -m metrics.isolation.cli score --user metrics/isolation/data/artifacts/user.json --json
```

## HTTP (프론트 연동)

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- `GET /isolation/ready` — `ref.json` 준비 여부
- `POST /isolation/analyze` — `user_video` multipart 업로드 → isolation 점수

통합 `POST /video/analyze`(6 metric)와 **별도** — 오케스트레이터 미사용.

## Flutter

`dance_app` Studio → 촬영 → 분석 시 `POST /isolation/analyze` 호출.

- Windows: `http://127.0.0.1:8000`
- Android 에뮬레이터: `http://10.0.2.2:8000`
- 실기기: `flutter run --dart-define=API_BASE_URL=http://<PC_IP>:8000`
