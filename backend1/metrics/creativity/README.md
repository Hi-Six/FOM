# Creativity metric

영상 또는 이미지 **쌍**을 비교해 창의성 점수(0~100)를 산출합니다.  
미디어 없이 JSON·샘플만으로 점수를 내는 기능은 **없습니다.**

## 보정 체크리스트 (두 영상 댄스 비교)

### 반드시 맞출 것

- [ ] **영상 전체 균등 샘플**: `--num-frames` 로 추출된 전체 프레임에서 동일 간격 샘플
- [ ] (선택) **춤 시작 시점**: `--auto-detect-start` 또는 `--user-offset` / `--ref-offset`
- [ ] **메인 댄서**: 화면 중앙 72% crop 후 MediaPipe (배경 인물 완화)
- [ ] **신체 스케일**: Mid-Hip 원점 + torso 길이 정규화
- [ ] **비교 특징**: `normalized_landmarks`, `joint_angles`, `bone_vectors`

### 가능하면 맞출 것

- [ ] **미러 보정**: `--apply-mirror` (기본 on) — 좌우 관절 스왑
- [ ] **정렬 방식**: `--alignment index|time|dtw` (템포 차이 시 `dtw`)
- [ ] **visibility**: `--visibility-threshold 0.5` — 저품질 프레임 제외

### MVP 이후 (본 폴더 밖 협의)

- [ ] 같은 음악 **오디오 비트/온셋** 자동 동기화
- [ ] YOLO 다인물 + 중앙 트래킹
- [ ] 카메라 roll / 측면 시점 보정

## 영상에서 추출하는 데이터

| 필드 | 설명 |
|------|------|
| `landmarks` | 원본 33관절 + visibility (품질 필터용) |
| `normalized_landmarks` | Mid-Hip·torso 정규화 좌표 |
| `joint_angles` | 관절 각(도) — 시점에 강건 |
| `bone_vectors` | 뼈 방향 벡터 |
| `time_sec` | 원본 영상 기준 시각 (offset·time/dtw 정렬) |
| `main_dancer_center_score` | 화면 중앙에 가까울수록 높음 |

## CLI

```powershell
cd C:\ai-x\FOM\backend1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
```

**MediaPipe 0.10.31+:** `mp.solutions` 가 없습니다. creativity 는 **Tasks API** 를 쓰며, 첫 실행 시 `models/pose_landmarker_lite.task` 를 자동 다운로드합니다.

### 출력 폴더 (기본)

분석 결과는 **`metrics/creativity/output/`** 에 저장됩니다.

| 경로 | 내용 |
|------|------|
| `output/creativity_score_YYYYMMDD_HHMMSS.json` | 창의성 점수 (기본, `-o` 생략 시) |
| `output/extractions/user.creativity.json` | 사용자 추출 (기본 저장) |
| `output/extractions/reference.creativity.json` | 레퍼런스 추출 |

`output/` 는 `.gitignore` 로 Git 제외됩니다.

### 영상 vs 영상 (CMD 한 줄)

```cmd
cd /d C:\ai-x\FOM\backend1
set PYTHONPATH=C:\ai-x\FOM\backend1
python -m metrics.creativity --user "C:\Users\804\Desktop\user.mp4" --reference "C:\Users\804\Desktop\ref.mp4" --num-frames 30 --alignment dtw --apply-mirror
```

`-o` / `--save-dir` 생략 시 `output/` 에 자동 저장. 터미널에는 **요약**만 출력되고, 상세는 JSON 파일에 저장됩니다. (`--json` 으로 전체 JSON stdout 가능)

### 고정 파일명으로 저장

```cmd
python -m metrics.creativity --user user.mp4 --reference ref.mp4 --num-frames 30 --auto-detect-start --alignment dtw -o metrics\creativity\output\creativity_score.json
```

## 파이프라인

```text
미디어 쌍 → 전체 프레임 추출(중앙 crop) → 영상 전체 균등 N프레임 샘플 → 미러·visibility
  → index|time|dtw 정렬 → score_creativity (0~100)
```

## 출력 JSON

`inputs`, `preprocess`, `alignment`, `creativity` (score, breakdown, frame_diffs)
