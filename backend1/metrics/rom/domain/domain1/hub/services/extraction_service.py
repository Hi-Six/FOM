import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
from typing import Dict, List, Literal, Optional, Tuple

from .pose_geometry import (
    LANDMARKS_FOR_ROM,
    compute_bone_vectors,
    compute_joint_angles,
)

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

EXTRACTION_SCHEMA_ROM = "rom_v1"
EXTRACTION_SCHEMA_FULL = "full_v1"
DEFAULT_TARGET_FPS_ROM = 15.0

ExtractionMode = Literal["rom", "full"]


def resolve_sample_stride(
    source_fps: float,
    target_fps: Optional[float] = DEFAULT_TARGET_FPS_ROM,
    frame_stride: Optional[int] = None,
) -> int:
    """MediaPipe 처리 간격. frame_stride 우선, target_fps<=0 이면 전체 프레임."""
    if frame_stride is not None:
        return max(1, int(frame_stride))
    if target_fps is None or target_fps <= 0:
        return 1
    if source_fps <= 0:
        source_fps = 30.0
    if target_fps >= source_fps:
        return 1
    return max(1, int(round(source_fps / target_fps)))


def _mediapipe_landmark_df(
    video_path: str,
    *,
    target_fps: Optional[float] = DEFAULT_TARGET_FPS_ROM,
    frame_stride: Optional[int] = None,
) -> Tuple[pd.DataFrame, float, int, int, int]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")

    source_fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
    source_total_frames: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = resolve_sample_stride(source_fps, target_fps, frame_stride)

    cols = [
        f"{name}_{coord}"
        for name in LANDMARK_NAMES
        for coord in ("x", "y", "z", "vis")
    ]
    raw_rows: List[List[float]] = []
    source_frame_indices: List[int] = []

    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = pose.process(rgb)
        if result.pose_landmarks:
            row: List[float] = []
            for lm in result.pose_landmarks.landmark:
                row.extend([lm.x, lm.y, lm.z, lm.visibility])
            raw_rows.append(row)
        else:
            raw_rows.append([np.nan] * len(cols))
        source_frame_indices.append(frame_idx)
        frame_idx += 1

    cap.release()
    pose.close()

    if not raw_rows:
        raise ValueError("영상에서 처리할 프레임이 없습니다.")

    df = pd.DataFrame(raw_rows, columns=cols)
    df["source_frame_index"] = source_frame_indices

    df = df.interpolate(method="linear", limit_direction="both")
    df = df.ffill().bfill()

    smooth_window = 3 if stride <= 2 else 1
    numeric_cols = cols
    df[numeric_cols] = (
        df[numeric_cols]
        .rolling(window=smooth_window, min_periods=1, center=True)
        .mean()
    )

    return df, source_fps, source_total_frames, stride, len(raw_rows)


def _row_to_landmarks(row: pd.Series, names: Tuple[str, ...]) -> Dict[str, dict]:
    landmarks: Dict[str, dict] = {}
    for name in names:
        landmarks[name] = {
            "x": float(row[f"{name}_x"]),
            "y": float(row[f"{name}_y"]),
            "z": float(row[f"{name}_z"]),
            "visibility": float(row[f"{name}_vis"]),
        }
    return landmarks


def _normalize_landmarks(landmarks: Dict[str, dict]) -> Dict[str, dict]:
    mid_hip_x = (landmarks["left_hip"]["x"] + landmarks["right_hip"]["x"]) / 2
    mid_hip_y = (landmarks["left_hip"]["y"] + landmarks["right_hip"]["y"]) / 2
    mid_hip_z = (landmarks["left_hip"]["z"] + landmarks["right_hip"]["z"]) / 2

    mid_shoulder_x = (
        landmarks["left_shoulder"]["x"] + landmarks["right_shoulder"]["x"]
    ) / 2
    mid_shoulder_y = (
        landmarks["left_shoulder"]["y"] + landmarks["right_shoulder"]["y"]
    ) / 2
    mid_shoulder_z = (
        landmarks["left_shoulder"]["z"] + landmarks["right_shoulder"]["z"]
    ) / 2

    torso_length = float(
        np.sqrt(
            (mid_shoulder_x - mid_hip_x) ** 2
            + (mid_shoulder_y - mid_hip_y) ** 2
            + (mid_shoulder_z - mid_hip_z) ** 2
        )
    )
    if torso_length < 1e-6:
        torso_length = 1.0

    normalized: Dict[str, dict] = {}
    for name, lm in landmarks.items():
        normalized[name] = {
            "x": float((lm["x"] - mid_hip_x) / torso_length),
            "y": float((lm["y"] - mid_hip_y) / torso_length),
            "z": float((lm["z"] - mid_hip_z) / torso_length),
        }
    return normalized


def _build_frames_from_df(
    df: pd.DataFrame,
    source_fps: float,
    mode: ExtractionMode,
) -> List[dict]:
    rom_names = tuple(sorted(LANDMARKS_FOR_ROM))
    all_names = tuple(LANDMARK_NAMES)
    landmark_names = rom_names if mode == "rom" else all_names

    frames_output: List[dict] = []
    for seq_i, (_, row) in enumerate(df.iterrows()):
        landmarks = _row_to_landmarks(row, landmark_names)
        normalized_landmarks = _normalize_landmarks(landmarks)
        joint_angles = compute_joint_angles(normalized_landmarks)

        source_idx = int(row["source_frame_index"])
        frame: Dict[str, object] = {
            "frame_index": seq_i,
            "source_frame_index": source_idx,
            "time_sec": round(source_idx / source_fps, 4),
            "joint_angles": joint_angles,
        }

        if mode == "full":
            full_landmarks = _row_to_landmarks(row, all_names)
            full_normalized = _normalize_landmarks(full_landmarks)
            frame["landmarks"] = full_landmarks
            frame["normalized_landmarks"] = full_normalized
            frame["bone_vectors"] = compute_bone_vectors(full_normalized)

        frames_output.append(frame)

    return frames_output


def _extraction_sampling_meta(
    source_fps: float,
    source_total_frames: int,
    sample_stride: int,
    processed_frames: int,
    target_fps: Optional[float],
    frame_stride: Optional[int],
) -> Dict[str, object]:
    effective_target = (
        None if sample_stride <= 1 else round(source_fps / sample_stride, 2)
    )
    return {
        "source_fps": source_fps,
        "source_total_frames": source_total_frames,
        "sample_stride": sample_stride,
        "extraction_target_fps": target_fps if frame_stride is None else None,
        "effective_sample_fps": effective_target,
        "total_frames": processed_frames,
    }


def extract_dance_data(
    video_path: str,
    *,
    target_fps: Optional[float] = None,
    frame_stride: Optional[int] = None,
) -> dict:
    """Accuracy용 full 추출. target_fps 미지정·0 이하면 전체 프레임."""
    df, source_fps, source_total, stride, n_proc = _mediapipe_landmark_df(
        video_path,
        target_fps=target_fps,
        frame_stride=frame_stride,
    )
    frames_output = _build_frames_from_df(df, source_fps, mode="full")
    meta = _extraction_sampling_meta(
        source_fps, source_total, stride, n_proc, target_fps, frame_stride
    )
    return {
        "schema": EXTRACTION_SCHEMA_FULL,
        "fps": source_fps,
        **meta,
        "frames": frames_output,
    }


def extract_rom_data(
    video_path: str,
    *,
    target_fps: Optional[float] = DEFAULT_TARGET_FPS_ROM,
    frame_stride: Optional[int] = None,
) -> dict:
    """ROM 전용: joint_angles + time_sec만 (기본 target_fps=15)."""
    df, source_fps, source_total, stride, n_proc = _mediapipe_landmark_df(
        video_path,
        target_fps=target_fps,
        frame_stride=frame_stride,
    )
    frames_output = _build_frames_from_df(df, source_fps, mode="rom")
    meta = _extraction_sampling_meta(
        source_fps, source_total, stride, n_proc, target_fps, frame_stride
    )
    return {
        "schema": EXTRACTION_SCHEMA_ROM,
        "fps": source_fps,
        **meta,
        "frames": frames_output,
    }
