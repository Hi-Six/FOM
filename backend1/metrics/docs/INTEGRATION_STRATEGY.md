# 6-Metric 통합 전략 및 병렬 처리 설계

> 작성일: 2026-05-21  
> 기준 문서: `metrics/docs/ARCHITECTURE.md`  
> 대상 파일: `backend1/main.py`, `backend1/routers/video.py`

---

## 1. 현재 상태 진단

### 1.1 metric별 `score_*` 함수 구현 여부

| metric | `score_*` 위치 | 입력 타입 | 구현 상태 |
|--------|---------------|----------|----------|
| **accuracy** | `metrics/rom/domain/domain1/hub/services/scoring/accuracy_scorer.py` | `aligned_pairs` | ✅ 구현 완료 |
| **creativity** | `metrics/creativity/creativity.py :: score_creativity` | `aligned_pairs` | ✅ 구현 완료 |
| **isolation** | `metrics/isolation/score.py :: score_isolation` | `aligned_pairs` | ✅ 구현 완료 |
| **power** | `metrics/power/__init__.py :: score_power` | `user_extraction` | ✅ 구현 완료 |
| **rhythm** | `metrics/rhythm/services/scoring/rhythm_scorer.py :: score_rhythm_from_extraction` | `user_extraction` | ✅ 구현 완료 |
| **rom** | `metrics/rom/domain/domain1/hub/services/scoring/rom_scorer.py :: score_rom` | `aligned_pairs` | ✅ 구현 완료 |

### 1.2 metric별 개별 라우터 현황

| metric | 라우터 위치 | prefix | main.py 등록 여부 |
|--------|-----------|--------|-----------------|
| **accuracy** | 없음 (CLI 스크립트만) | — | ❌ 미등록 |
| **creativity** | CLI only | — | ❌ 미등록 |
| **isolation** | `metrics/isolation/router.py` | `/isolation` | ❌ **미등록** (구 버전에서 제거됨) |
| **power** | `metrics/power/routers/video.py` | `/power` | ❌ **미등록** |
| **rhythm** | `metrics/rhythm/routers/video.py` | `/video` | ⚠️ 등록됨 — **prefix 충돌** |
| **rom** | `routers/video.py` | `/video` | ✅ 등록됨 |

### 1.3 현재 main.py 문제점

```python
# 현재 (충돌 발생)
app.include_router(rhythm_router)   # prefix=/video → POST /video/analyze 선점
app.include_router(video_router)    # prefix=/video → 동일 경로, ROM 라우터 가려짐
```

**FastAPI는 먼저 등록된 라우터가 우선**이므로,  
`POST /video/analyze` 는 rhythm이, `POST /video/extract` 도 rhythm이 처리함.  
ROM 통합 채점(`run_analyze`)은 **사실상 사용 불가** 상태.

---

## 2. 통합 목표 구조

ARCHITECTURE.md 기준 최종 형태:

```
POST /video/extract     → 각 metric 추출 API (or 통합 추출)
POST /video/analyze     → 오케스트레이터: 6 score_* 병렬 호출 후 병합
POST /isolation/analyze → isolation 전용 (YOLO, 별도 파이프라인)
POST /power/score       → power 전용 (추출+채점 one-shot)
POST /rhythm/analyze    → rhythm 전용 (beat 포함)
GET  /health
```

---

## 3. 라우터 prefix 충돌 해결 전략

### 전략: metric별 고유 prefix 사용

| metric | 권장 prefix | 변경 필요 |
|--------|------------|----------|
| rhythm | `/rhythm` (현재 `/video` → 변경) | ✅ |
| power | `/power` (현재대로) | — |
| isolation | `/isolation` (현재대로) | — |
| 통합 오케스트레이터 | `/video` (ROM + 6채점) | — |

### 조치 내용

```python
# main.py 최종 목표
from routers.video import router as video_router           # /video — 통합 오케스트레이터
from metrics.isolation.router import router as isolation_router  # /isolation
from metrics.power.routers.video import router as power_router   # /power
from metrics.rhythm.routers.video import router as rhythm_router # /rhythm (prefix 변경 필요)

app.include_router(video_router)      # 통합: /video/analyze, /video/extract, /video/compare
app.include_router(isolation_router)  # 독립: /isolation/analyze, /isolation/ready
app.include_router(power_router)      # 독립: /power/extract, /power/score
app.include_router(rhythm_router)     # 독립: /rhythm/analyze, /rhythm/extract, /rhythm/visualize
```

> **rhythm 라우터 수정**: `metrics/rhythm/routers/video.py`에서  
> `router = APIRouter(prefix="/video", ...)` → `router = APIRouter(prefix="/rhythm", ...)`

---

## 4. 통합 오케스트레이터 설계 (`POST /video/analyze`)

### 4.1 요청 스펙

```json
{
  "user_json": "20260521_120000_abc123.json",
  "reference_json": "ref_idol_A.json",
  "alignment_method": "time",
  "user_offset_sec": 0.0,
  "ref_offset_sec": 0.0,
  "metrics": ["accuracy", "creativity", "isolation", "power", "rhythm", "rom"]
}
```

`metrics` 키로 호출할 채점 서비스를 선택 가능 (기본: 6개 전체).

### 4.2 오케스트레이터 처리 흐름

```
1. [동기] user_json, reference_json 로드·검증
2. [동기] aligned_pairs 생성 (alignment_method: time/dtw)
3. [비동기 병렬] asyncio.gather + run_in_executor 로 score_* 6개 동시 실행
4. [동기] 결과 병합 → total_score, grade 산출
5. [응답] scores + alignment + meta
```

### 4.3 입력 분기

ARCHITECTURE.md §4 기준:

| metric | 오케스트레이터가 넘기는 인자 |
|--------|--------------------------|
| accuracy | `aligned_pairs` |
| creativity | `aligned_pairs` |
| isolation | `aligned_pairs` |
| rom | `aligned_pairs` |
| power | `user_extraction` (사용자 JSON 전체) |
| rhythm | `user_extraction` |

---

## 5. 병렬 처리 구현 전략

### 5.1 기본 원칙

- 모든 `score_*` 함수는 **동기(sync)** 함수 — IO 없음, CPU 연산만
- FastAPI 라우터는 `async` 핸들러 사용
- `asyncio.gather` + `loop.run_in_executor(None, ...)` 로 동기 함수를 스레드풀에서 병렬 실행

### 5.2 구현 코드 패턴

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

from metrics.accuracy.service import score_accuracy       # aligned_pairs
from metrics.creativity.creativity import score_creativity # aligned_pairs
from metrics.isolation.score import score_isolation        # aligned_pairs
from metrics.rom.domain.domain1.hub.services.scoring.rom_scorer import score_rom  # aligned_pairs
from metrics.power import score_power                      # user_extraction
from metrics.rhythm import score_rhythm_from_extraction    # user_extraction

_executor = ThreadPoolExecutor(max_workers=6)

async def run_all_scores(
    aligned_pairs: list,
    user_extraction: dict,
    enabled_metrics: list[str],
) -> dict:
    loop = asyncio.get_event_loop()

    tasks = {}

    if "accuracy" in enabled_metrics:
        tasks["accuracy"] = loop.run_in_executor(
            _executor, score_accuracy, aligned_pairs
        )
    if "creativity" in enabled_metrics:
        tasks["creativity"] = loop.run_in_executor(
            _executor, score_creativity, aligned_pairs
        )
    if "isolation" in enabled_metrics:
        tasks["isolation"] = loop.run_in_executor(
            _executor, score_isolation, aligned_pairs
        )
    if "rom" in enabled_metrics:
        tasks["rom"] = loop.run_in_executor(
            _executor, score_rom, aligned_pairs
        )
    if "power" in enabled_metrics:
        tasks["power"] = loop.run_in_executor(
            _executor, score_power, user_extraction
        )
    if "rhythm" in enabled_metrics:
        tasks["rhythm"] = loop.run_in_executor(
            _executor, score_rhythm_from_extraction, user_extraction
        )

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    scores = {}
    for key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            scores[key] = {"score": 0.0, "error": str(result), "breakdown": {}}
        else:
            scores[key] = result

    return scores
```

### 5.3 total_score 산출

```python
METRIC_WEIGHTS = {
    "accuracy":   1.0,
    "creativity": 1.0,
    "isolation":  1.0,
    "power":      1.0,
    "rhythm":     1.0,
    "rom":        1.0,
}

def compute_total(scores: dict) -> tuple[float, str]:
    total = 0.0
    weight_sum = 0.0
    for key, result in scores.items():
        s = result.get("score", 0.0)
        w = METRIC_WEIGHTS.get(key, 1.0)
        total += s * w
        weight_sum += w
    avg = round(total / weight_sum, 2) if weight_sum > 0 else 0.0
    grade = _to_grade(avg)
    return avg, grade

def _to_grade(score: float) -> str:
    if score >= 90: return "S"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    return "D"
```

### 5.4 병렬 실행 성능 특성

| 항목 | 내용 |
|------|------|
| 실행 방식 | `ThreadPoolExecutor(max_workers=6)` — GIL 해제 NumPy 연산에 유리 |
| 전체 응답 시간 | max(개별 score 시간) ≈ 가장 느린 metric 1개 시간 |
| 예상 지연 | JSON 로드·정렬 ~50ms + score 병렬 ~100~300ms = **총 ~400ms** |
| 실패 처리 | `return_exceptions=True` → 개별 실패는 `error` 필드로 표시, 나머지 응답 정상 |
| 메모리 | `aligned_pairs`·`user_extraction` 읽기 전용 공유 — 복사 없음 |

### 5.5 MediaPipe 동시 실행 주의사항

- 추출(extract) 단계에서 MediaPipe PoseLandmarker 인스턴스를 **스레드 간 공유하지 말 것**
- 각 추출 API(`/power/extract`, `/rhythm/extract` 등)는 **요청마다 독립 세션** 사용
- `/video/analyze` 오케스트레이터는 추출 없이 JSON만 처리 → MediaPipe 비관련

---

## 6. 단계별 작업 계획

### Phase 1 — 라우터 prefix 정리 (즉시 가능)

```
[ ] metrics/rhythm/routers/video.py : prefix "/video" → "/rhythm"
[ ] main.py : isolation_router, power_router 등록 추가
[ ] main.py : rhythm_router prefix 변경 후 재등록
```

### Phase 2 — 통합 오케스트레이터 구현

```
[ ] routers/video.py : POST /video/analyze 에 6채점 asyncio.gather 병렬 호출 추가
[ ] 신규 파일: services/orchestrator.py (run_all_scores, compute_total)
[ ] 각 metric의 score_* 임포트 경로 확인 및 연결
```

### Phase 3 — 추출 통합 (선택)

```
[ ] POST /video/extract : 현재 ROM 전용 → metric 파라미터로 선택 추출 위임
    예: ?metrics=rom,power,rhythm 으로 해당 metric 추출만 실행
```

### Phase 4 — 검증

```
[ ] uvicorn main:app 기동 후 GET /openapi.json 라우트 중복 확인
[ ] POST /video/analyze 통합 채점 테스트
[ ] POST /rhythm/analyze, /power/score, /isolation/analyze 독립 동작 확인
```

---

## 7. 최종 엔드포인트 맵

```
# 통합 (routers/video.py, prefix=/video)
POST /video/analyze          ← 6-metric 병렬 채점 오케스트레이터
POST /video/analyze/json     ← 저장 JSON 2개 → 채점
POST /video/extract          ← 영상 → ROM/full 추출
POST /video/compare          ← ROM 전용 비교 (디버그)
GET  /video/json/{filename}  ← 추출 JSON 다운로드
GET  /video/data/{filename}  ← annotated MP4

# Isolation 전용 (metrics/isolation/router.py, prefix=/isolation)
GET  /isolation/ready
POST /isolation/analyze

# Power 전용 (metrics/power/routers/video.py, prefix=/power)
POST /power/extract
POST /power/score

# Rhythm 전용 (metrics/rhythm/routers/video.py, prefix=/rhythm ← 변경 필요)
POST /rhythm/analyze
POST /rhythm/extract
POST /rhythm/visualize
POST /rhythm/compare-visualize
GET  /rhythm/json/{filename}
GET  /rhythm/video-data/{filename}

# 공통
GET  /health
```

---

## 8. 경계 규칙 재확인

| 규칙 | 이유 |
|------|------|
| `score_*` 함수는 **영상 재추출 없음** | analyze 요청 지연 방지 |
| metric 서비스끼리 **import 금지** | 결합도 0, 독립 배포 가능 |
| `aligned_pairs` 는 **읽기 전용** | 스레드 안전, 복사 비용 없음 |
| 개별 metric 라우터는 **독립 prefix** | 통합 `/video` 경로 오염 방지 |
| 실패한 metric은 **error 필드**로 응답 | 부분 실패 시 다른 metric 결과 보존 |
