# Role
You are an expert Python Backend Developer and Computer Vision Engineer. Your task is to build the core Video Data Extraction Module for a Street Dance Analysis MVP.

# Project Context

## 프로젝트 개요
- **프로젝트명:** 폼미쳤다 (FOM) - "너 오늘 춤 폼 미쳤다" 할 때 그 폼! 진단받고 폼 확인하는 곳
- **팀명:** Hi-Six - "인사는 가볍게, 퀄리티는 높게(High)! 완벽한 호흡으로 뭉친 6명의 인재들"
- **Domain:** AI 기반 10대 대상 스트릿 댄스 수준 판단 및 진로 지도 플랫폼
- **캐치프레이즈:** "방구석이 나만의 무대로, AI가 찾아주는 나의 댄스 DNA"

## 프로젝트 목적
1. AI 비전 기술을 활용해 10대 청소년의 스트릿 댄스 동작을 전문가 영상과 정밀하게 비교·평가
2. 분석 데이터를 기반으로 맞춤형 교정 피드백과 LLM 중심의 실질적인 진로 지도 가이드 제공
3. 1주일 내 웹 MVP 플랫폼 구축

## 아키텍처 설계
- **Architecture:** We have 6 separate scoring functions (ROM, Power, Isolation, Rhythm, Creativity, Accuracy) that will be developed by different team members. 
- **Goal:** To prevent server overload and ensure parallel development, you must build **ONE common extraction module**. This module will process an uploaded video once, extract the 3D landmarks, clean the data, normalize it, and return a standardized JSON array. This JSON will then be passed as an argument to the 6 scoring functions.
- **Data Flow:** 영상 업로드 → 공통 추출 모듈(domain1) → 표준 JSON → 6개 채점 함수 → LLM 피드백 생성 → 결과 시각화

# Tech Stack & Constraints
- Python 3.9+
- `opencv-python` (cv2) for video processing.
- `mediapipe` (Pose solution) for 3D landmark extraction.
- `numpy`, `pandas`, `scipy` for mathematical operations, data smoothing, and interpolation.
- **Performance:** This is an MVP. Optimize for speed. If YOLO11 integration for bounding box tracking is too complex for a 1-week MVP, skip it and rely entirely on `mediapipe` with strict data smoothing.

# Pipeline Requirements (Crucial)
You must implement a class or function (e.g., `extract_dance_data(video_path)`) that strictly follows these 4 steps:

1. **Meta Data Extraction:**
   - Extract and store the `fps` (Frames Per Second) and `total_frames` using OpenCV. This is strictly required for the 'Rhythm' and 'Accuracy' scoring modules to align time.

2. **Raw Landmark Extraction:**
   - Run MediaPipe Pose on every frame.
   - Extract `x`, `y`, `z`, and `visibility` for all 33 landmarks.

3. **Data Smoothing & Interpolation (Mandatory):**
   - Dance videos have fast motions, causing MediaPipe to temporarily lose track or coordinates to jitter.
   - Use `pandas` `.interpolate(method='linear')` to fill missing frames (NaN values).
   - Apply a Moving Average filter (e.g., `rolling(window=3).mean()`) to remove high-frequency jitter. If this is skipped, the 'Power' (acceleration) scoring function will break.

4. **Normalization (Crucial for Accuracy Scoring):**
   - The 'Accuracy' module compares users with reference dancers of different body proportions. You must apply a 2-step normalization to eliminate body scale and position differences:
   - **Step A (Translation):** Calculate the 'Mid-Hip' (average of left_hip and right_hip). Shift all 33 coordinates so Mid-Hip becomes `(0,0,0)`.
   - **Step B (Scaling):** Calculate the 'Torso Length' (distance between Mid-Shoulder and Mid-Hip). Divide all translated coordinates by this Torso Length.
   - Create a `normalized_landmarks` dictionary with these final values. This ensures coordinates represent relative body proportions, unaffected by actual height or camera distance.

# Expected Output (JSON Schema)
The function must return a Python Dictionary (convertible to JSON) exactly matching this schema:

```json
{
  "fps": 30.0,
  "total_frames": 1800,
  "frames": [
    {
      "frame_index": 0,
      "time_sec": 0.0,
      "landmarks": {
        "left_shoulder": {"x": 0.52, "y": 0.31, "z": -0.15, "visibility": 0.99},
        // ... all 33 landmarks
      },
      "normalized_landmarks": {
        "left_shoulder": {"x": -0.2, "y": 0.8, "z": -0.1} 
        // ... all 33 scaled & translated landmarks relative to Mid-Hip
      }
    }
  ]
}