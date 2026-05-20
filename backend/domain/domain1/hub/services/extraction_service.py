import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from ...models.transfer.video_data import VideoExtractionResult, FrameData
from ...models.bases.landmark import Landmark, NormalizedLandmark

# MediaPipe의 33개 랜드마크 이름 매핑
LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

LEFT_HIP_IDX = 23
RIGHT_HIP_IDX = 24


def extract_dance_data(video_path: str) -> dict:
    """
    4단계 파이프라인:
    1) 메타데이터 추출 (fps, total_frames)
    2) MediaPipe로 원시 랜드마크 추출
    3) 보간 + 이동평균 스무딩
    4) 정규화 2단계
       - Step A: Mid-Hip 기준 이동 → Mid-Hip을 (0,0,0)으로
       - Step B: Torso Length(Mid-Shoulder↔Mid-Hip 거리)로 나눠 체형 스케일 제거
    """
    # ── Step 1: 메타데이터 추출 ──────────────────────────────────────────────
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")

    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # ── Step 2: 원시 랜드마크 추출 ──────────────────────────────────────────
    # 컬럼: landmark_name_x/y/z/vis
    n_landmarks = len(LANDMARK_NAMES)
    cols = [f"{name}_{coord}" for name in LANDMARK_NAMES for coord in ("x", "y", "z", "vis")]
    raw_rows: List[Optional[List[float]]] = []

    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = pose.process(rgb)
        if result.pose_landmarks:
            row: List[float] = []
            for lm in result.pose_landmarks.landmark:
                row.extend([lm.x, lm.y, lm.z, lm.visibility])
            raw_rows.append(row)
        else:
            # 랜드마크 미검출 → NaN 행 삽입 (보간 대상)
            raw_rows.append([np.nan] * len(cols))

    cap.release()
    pose.close()

    # ── Step 3: 보간 + 이동평균 스무딩 ─────────────────────────────────────
    df = pd.DataFrame(raw_rows, columns=cols)

    # 선형 보간으로 NaN 채우기 (첫·끝 프레임은 ffill/bfill로 처리)
    df = df.interpolate(method="linear", limit_direction="both")
    df = df.ffill().bfill()

    # 이동평균으로 고주파 지터 제거 (window=3)
    df = df.rolling(window=3, min_periods=1, center=True).mean()

    actual_frames = len(df)

    # ── Step 4: 정규화 + 최종 JSON 조립 ─────────────────────────────────────
    frames_output: List[dict] = []

    for fi, row in df.iterrows():
        landmarks: Dict[str, dict] = {}
        for name in LANDMARK_NAMES:
            landmarks[name] = {
                "x": float(row[f"{name}_x"]),
                "y": float(row[f"{name}_y"]),
                "z": float(row[f"{name}_z"]),
                "visibility": float(row[f"{name}_vis"]),
            }

        # ── Step A: Translation — Mid-Hip을 원점(0,0,0)으로 이동 ──────────
        mid_hip_x = (landmarks["left_hip"]["x"] + landmarks["right_hip"]["x"]) / 2
        mid_hip_y = (landmarks["left_hip"]["y"] + landmarks["right_hip"]["y"]) / 2
        mid_hip_z = (landmarks["left_hip"]["z"] + landmarks["right_hip"]["z"]) / 2

        # ── Step B: Scaling — Torso Length으로 나눠 체형 스케일 제거 ────────
        # Mid-Shoulder = (left_shoulder + right_shoulder) / 2
        mid_shoulder_x = (landmarks["left_shoulder"]["x"] + landmarks["right_shoulder"]["x"]) / 2
        mid_shoulder_y = (landmarks["left_shoulder"]["y"] + landmarks["right_shoulder"]["y"]) / 2
        mid_shoulder_z = (landmarks["left_shoulder"]["z"] + landmarks["right_shoulder"]["z"]) / 2

        # Torso Length = Mid-Shoulder ↔ Mid-Hip 유클리드 거리
        torso_length = float(np.sqrt(
            (mid_shoulder_x - mid_hip_x) ** 2 +
            (mid_shoulder_y - mid_hip_y) ** 2 +
            (mid_shoulder_z - mid_hip_z) ** 2
        ))
        # 0으로 나누기 방지 (매우 드문 케이스)
        if torso_length < 1e-6:
            torso_length = 1.0

        normalized_landmarks: Dict[str, dict] = {}
        for name in LANDMARK_NAMES:
            normalized_landmarks[name] = {
                "x": float((landmarks[name]["x"] - mid_hip_x) / torso_length),
                "y": float((landmarks[name]["y"] - mid_hip_y) / torso_length),
                "z": float((landmarks[name]["z"] - mid_hip_z) / torso_length),
            }

        frames_output.append({
            "frame_index": int(fi),
            "time_sec": round(int(fi) / fps, 4),
            "landmarks": landmarks,
            "normalized_landmarks": normalized_landmarks,
        })

    return {
        "fps": fps,
        "total_frames": actual_frames,
        "frames": frames_output,
    }
