# Role

You are an expert **Python backend / computer vision** engineer and a coordinator for the **폼미쳤다 (FOM)** MVP. Primary ownership: `backend/domain/domain1` (video extraction, comparison, scoring). Secondary context: Flutter app `dance_app` (UI mock → API 연동 예정).

# Project Context

## 프로젝트 개요

- **프로젝트명:** 폼미쳤다 (FOM) — "너 오늘 춤 폼 미쳤다" 할 때 그 폼
- **팀명:** Hi-Six
- **타깃:** 10대 — 스트릿 댄스 수준 판단 및 진로 가이드
- **캐치프레이즈:** "방구석이 나만의 무대로, AI가 찾아주는 나의 댄스 DNA"

## 프로젝트 목적

1. 사용자 영상과 전문가(레퍼런스) 영상을 AI 비전으로 비교·평가
2. 6개 차원 점수 + LLM 맞춤 피드백·진로 가이드
3. **1주일 MVP** — 모바일 앱(Flutter) + FastAPI 백엔드

## 모노레포 구조

```
app/
├── CLAUDE.md                          ← 이 파일 (AI 개발 가이드)
├── backend/                           ← FastAPI, domain1
│   ├── main.py
│   ├── routers/video.py
│   └── domain/domain1/
│       ├── hub/services/              ← extraction, comparison, scoring, visualizer
│       ├── models/                    ← Pydantic (landmark, video_data, compare_request)
│       ├── video_data/                ← annotated MP4, video_json/*.json
│       └── docs/                      ← 상세 설계·현황 (아래 참고)
└── dance_app/                         ← Flutter MVP (Mock → 백엔드 연동 예정)
    └── docs/APP_SCREEN_GUIDE.md       ← 화면·라우팅·UI 명세
```

## 아키텍처 (Hub-Spoke + One-Time Processing)

- **공통 추출 1회:** 업로드 영상 → MediaPipe → 스무딩 → 정규화 → 표준 JSON (`joint_angles`, `bone_vectors` 포함)
- **6개 채점 함수 (팀 병렬 개발):** ROM, Power, Isolation, Rhythm, Creativity, **Accuracy**
- **데이터 플로우:**
  ```
  [Flutter Studio] 영상 선택
       → POST /video/extract (사용자·전문가 각각)
       → video_json/{id}.json + annotated MP4 저장
       → POST /video/compare (JSON 파일명 2개)
       → Accuracy 등 점수 → (예정) LLM 피드백 → Feedback / Report UI
  ```

## 구현 단계 (2026-05-20 기준)

| Phase | 내용 | 상태 |
|-------|------|------|
| 1 | 비디오 추출 파이프라인 + `/video/extract` + JSON·오버레이 저장 | ✅ 완료 |
| 2 | 6개 채점 함수 | 🔄 진행 (~25%): **Accuracy** + `/video/compare` 완료 |
| 3 | LLM 피드백 | ⏳ 대기 |
| 4 | 앱–API 연동·시각화 | ⏳ Flutter는 Mock, 백엔드 CORS 준비됨 |

상세: `backend/domain/domain1/docs/IMPLEMENTATION_STATUS.md`

# Tech Stack

## Backend (`backend/`)

- Python 3.13.13
- **FastAPI** + **uvicorn** — REST API
- **OpenCV** — 비디오 메타·프레임
- **MediaPipe Pose** — 33 랜드마크 (YOLO11은 MVP에서 **미사용**, `requirements.txt` 주석)
- **NumPy, Pandas, SciPy** — 보간·스무딩·수치 연산
- **Pydantic v2** — 요청/응답 스키마 (추출 결과는 아직 plain `dict` 반환)

로컬 실행:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Swagger: http://localhost:8000/docs
```

## Frontend (`dance_app/`)

- Flutter 3.11+, Riverpod, go_router
- 5화면: Home → Studio → Loading → Feedback → Report (하단 탭 3 + 전체 화면 2)
- 현재 **Mock Repository**; 백엔드 연동 시 `/video/extract`, `/video/compare` 호출 예정

화면·라우트 상세: `dance_app/docs/APP_SCREEN_GUIDE.md`

# REST API (domain1)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/health` | 헬스체크 |
| `POST` | `/video/extract` | 영상 업로드 → 추출 JSON 저장 + 스켈레톤 오버레이 MP4 |
| `POST` | `/video/compare` | 저장된 JSON 2개 비교 (body: `user_json`, `reference_json`, `alignment_method`) |
| `GET` | `/video/json/{filename}` | 저장된 추출 JSON |
| `GET` | `/video/data/{filename}` | annotated MP4 |

**업로드 제한:** 확장자 `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` / 최대 **500MB**

**저장 경로:** `backend/domain/domain1/video_data/video_json/`, `video_data/*_annotated.mp4`

**`/video/extract` 응답 메타 (추가 필드):** `extraction_id`, `extraction_json`, `annotated_video` — compare 시 `extraction_json.filename` 사용

# Extraction Pipeline (필수)

구현: `backend/domain/domain1/hub/services/extraction_service.py` → `extract_dance_data(video_path)`

## 5단계 처리

1. **메타데이터:** OpenCV `fps`, `total_frames` (응답의 `total_frames`는 **실제 처리 프레임 수** `len(df)`)
2. **원시 랜드마크:** MediaPipe Pose, 33개 × `x,y,z,visibility`; 미검출 → NaN
3. **스무딩·보간 (필수):** `interpolate(linear)` → `ffill`/`bfill` → `rolling(window=3, center=True).mean()` — **Power** 채점용
4. **정규화 (Accuracy·ROM 등):**
   - **Step A:** Mid-Hip = `(left_hip + right_hip) / 2` → 원점 `(0,0,0)`
   - **Step B:** Torso Length = Mid-Shoulder ↔ Mid-Hip 거리로 나눔 (`torso_length < 1e-6` → `1.0`)
5. **기하 특징 (`pose_geometry.py`):** `normalized_landmarks` 기준
   - `joint_angles` — 관절 각도(도), **시점에 강건** → Accuracy **60%**
   - `bone_vectors` — 단위 방향 + `magnitude` → 코사인 유사도, Accuracy **40%**

## 표준 JSON 스키마 (프레임당)

```json
{
  "fps": 30.0,
  "total_frames": 120,
  "frames": [
    {
      "frame_index": 0,
      "time_sec": 0.0,
      "landmarks": {
        "left_shoulder": {"x": 0.52, "y": 0.31, "z": -0.15, "visibility": 0.99}
      },
      "normalized_landmarks": {
        "left_shoulder": {"x": -0.2, "y": 0.8, "z": -0.1}
      },
      "bone_vectors": {
        "left_upper_arm": {"x": 0.12, "y": -0.45, "z": 0.03, "magnitude": 0.35}
      },
      "joint_angles": {
        "left_elbow": 142.5,
        "right_knee": 165.2
      }
    }
  ]
}
```

- `normalized_landmarks`에는 **visibility 없음**
- 채점·비교 시 **`landmarks` 좌표 직접 비교 금지** (화면 위치·촬영 앵글 민감) — `VIEWPOINT_INVARIANCE.md` 참고

# Scoring (6 dimensions)

각 함수 입력: **Phase 1 표준 JSON** (단일 영상 또는 compare 시 정렬된 프레임 쌍).

| 함수 | 평가 요지 | 입력 힌트 | MVP 상태 |
|------|-----------|-----------|----------|
| **ROM** | 관절 가동 범위 | `joint_angles` min/max | ⏳ |
| **Power** | 가속도·폭발력 | 정규화 좌표 시계열 (스무딩 필수) | ⏳ |
| **Isolation** | 부위 독립성 | `bone_vectors`, 비목표 관절 정적도 | ⏳ |
| **Rhythm** | 박자·타이밍 | `fps`, `time_sec`, 동작 피크 | ⏳ |
| **Creativity** | 레퍼런스 대비 독창성 | 궤적/DTW 변형 | ⏳ |
| **Accuracy** | 레퍼런스 유사도 | `joint_angles` 60% + `bone_vectors` 코사인 40% | ✅ `accuracy_scorer.py` |

**비교 API:** `comparison_service.compute_comparison` — 프레임 정렬 `align_by_time` (MVP), DTW는 예정.

구현 위치: `backend/domain/domain1/hub/services/scoring/`

# Flutter 앱 (연동 가이드)

| 앱 화면 | 백엔드 대응 (목표) |
|---------|-------------------|
| Studio — 영상 업로드 | `POST /video/extract` (사용자) |
| (사전) 레퍼런스 | 전문가 영상도 동일 extract → JSON 파일명 보관 |
| Loading | extract + compare 폴링/대기 |
| Feedback | Accuracy, `frame_diffs`, annotated MP4 URL |
| Report | 6항목 점수 레이더 + LLM 카드 (Phase 3) |

앱 레이더 Mock 항목: ROM, Power, Rhythm, Isolation, Creativity — 백엔드 6함수와 **이름·의미 일치** 유지.

# 개발 원칙

1. **추출 모듈 1회만 수정** — 채점 로직은 `scoring/`에 추가, Hub 추출 파이프라인은 팀 공통
2. **MVP 속도 우선** — MediaPipe + 스무딩으로 충분; YOLO·무거운 DTW는 문서화 후 단계적 도입
3. **Accuracy는 각도·뼈 방향 우선** — `normalized_landmarks` 단독 L2/D TW 금지
4. **문서 동기화** — 동작·API 변경 시 `domain1/docs/IMPLEMENTATION_STATUS.md` 갱신

# 참고 문서

| 문서 | 용도 |
|------|------|
| `backend/domain/domain1/docs/PROJECT_CONTEXT.md` | 기획·문제 정의 |
| `backend/domain/domain1/docs/IMPLEMENTATION_STATUS.md` | 구현 현황·TODO |
| `backend/domain/domain1/docs/ARCHITECTURE.md` | 시스템·API·채점 설계 |
| `backend/domain/domain1/docs/CURRENT_LOGIC.md` | 추출·비교 실제 동작·한계 |
| `backend/domain/domain1/docs/COMPARISON_STRATEGY.md` | compare API·정렬·Accuracy |
| `backend/domain/domain1/docs/VIEWPOINT_INVARIANCE.md` | 시점 불변성·채점 데이터 선택 |
| `dance_app/docs/APP_SCREEN_GUIDE.md` | Flutter 화면·라우팅·Mock 현황 |
