# Isolation metric (로컬 + API)

## CLI

```powershell
cd backend1
python -m metrics.isolation.cli extract   # ref.json
python -m metrics.isolation.cli run --user-video metrics/isolation/data/raw/user.mp4
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
