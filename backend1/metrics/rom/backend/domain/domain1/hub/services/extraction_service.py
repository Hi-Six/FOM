import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from .pose_geometry import compute_bone_vectors, compute_joint_angles

# MediaPipe Tasks API 모델 경로
_MODEL_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "models" / "pose_landmarker_full.task"

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

def extract_dance_data(video_path: str) -> dict:
    """
    4단계 파이프라인:
    1) 메타데이터 추출 (fps, total_frames)
    2) MediaPipe로 원시 랜드마크 추출
    3) 보간 + 이동평균 스무딩
    4) 정규화 2단계
       - Step A: Mid-Hip 기준 이동 → Mid-Hip을 (0,0,0)으로
       - Step B: Torso Length(Mid-Shoulder↔Mid-Hip 거리)로 나눠 체형 스케일 제거
    5) bone_vectors / joint_angles (정규화 좌표 기준, Accuracy·코사인 비교용)
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

    # MediaPipe Tasks API (VIDEO 모드)
    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(_MODEL_PATH)),
        running_mode=VisionRunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frame_idx = 0
    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(frame_idx * 1000 / fps)
            
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
            
            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                row: List[float] = []
                for lm in result.pose_landmarks[0]:
                    row.extend([lm.x, lm.y, lm.z, lm.visibility])
                raw_rows.append(row)
            else:
                # 랜드마크 미검출 → NaN 행 삽입 (보간 대상)
                raw_rows.append([np.nan] * len(cols))
            frame_idx += 1

    cap.release()

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

        bone_vectors = compute_bone_vectors(normalized_landmarks)
        joint_angles = compute_joint_angles(normalized_landmarks)

        frames_output.append({
            "frame_index": int(fi),
            "time_sec": round(int(fi) / fps, 4),
            "landmarks": landmarks,
            "normalized_landmarks": normalized_landmarks,
            "bone_vectors": bone_vectors,
            "joint_angles": joint_angles,
        })

    return {
        "fps": fps,
        "total_frames": actual_frames,
        "frames": frames_output,
    }
