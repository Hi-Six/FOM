"""추출 JSON을 영상 프레임에 오버레이하여 video_data에 저장."""

from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from .pose_geometry import BONE_SEGMENTS

# domain1/video_data
VIDEO_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "video_data"

# MediaPipe Pose landmark index pairs (solutions.pose.POSE_CONNECTIONS)
_MP_POSE_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
)

# 화면에 각도 숫자를 붙일 관절 (landmark 이름)
ANGLE_LABEL_JOINTS = {
    "left_elbow": "left_elbow",
    "right_elbow": "right_elbow",
    "left_knee": "left_knee",
    "right_knee": "right_knee",
    "left_shoulder": "left_shoulder",
    "right_shoulder": "right_shoulder",
}

PANEL_WIDTH = 340
COLOR_LM = (0, 255, 128)
COLOR_NORM = (255, 180, 0)
COLOR_BONE = (255, 220, 0)
COLOR_ANGLE = (0, 255, 255)
COLOR_TEXT = (240, 240, 240)
COLOR_PANEL_BG = (24, 24, 28)


def ensure_video_data_dir() -> Path:
    VIDEO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEO_DATA_DIR


def _lm_pixel(lm: dict, w: int, h: int) -> Tuple[int, int]:
    return int(lm["x"] * w), int(lm["y"] * h)


def _mid_pixel(
    lms: Dict[str, dict], a: str, b: str, w: int, h: int
) -> Tuple[int, int]:
    mx = (lms[a]["x"] + lms[b]["x"]) / 2
    my = (lms[a]["y"] + lms[b]["y"]) / 2
    return int(mx * w), int(my * h)


def _resolve_lm_pixel(
    name: str, lms: Dict[str, dict], w: int, h: int
) -> Tuple[int, int]:
    if name == "mid_hip":
        return _mid_pixel(lms, "left_hip", "right_hip", w, h)
    if name == "mid_shoulder":
        return _mid_pixel(lms, "left_shoulder", "right_shoulder", w, h)
    return _lm_pixel(lms[name], w, h)


def _draw_skeleton_by_names(
    canvas: np.ndarray,
    lms: Dict[str, dict],
    connections: List[Tuple[str, str]],
    w: int,
    h: int,
    color: Tuple[int, int, int],
    thickness: int = 2,
) -> None:
    for a, b in connections:
        if a not in lms or b not in lms:
            continue
        p1 = _lm_pixel(lms[a], w, h)
        p2 = _lm_pixel(lms[b], w, h)
        cv2.line(canvas, p1, p2, color, thickness, cv2.LINE_AA)


# MediaPipe 인덱스 → 이름 (extraction_service.LANDMARK_NAMES 순서와 동일)
_LANDMARK_BY_INDEX = [
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

_SCREEN_CONNECTIONS: List[Tuple[str, str]] = [
    (_LANDMARK_BY_INDEX[i], _LANDMARK_BY_INDEX[j])
    for i, j in _MP_POSE_CONNECTIONS
    if i < len(_LANDMARK_BY_INDEX) and j < len(_LANDMARK_BY_INDEX)
]


def _draw_landmarks_overlay(
    frame: np.ndarray,
    frame_data: dict,
) -> np.ndarray:
    h, w = frame.shape[:2]
    lms = frame_data["landmarks"]
    out = frame.copy()

    _draw_skeleton_by_names(out, lms, _SCREEN_CONNECTIONS, w, h, COLOR_LM, 2)
    for name, lm in lms.items():
        if lm.get("visibility", 1.0) < 0.3:
            continue
        cv2.circle(out, _lm_pixel(lm, w, h), 4, COLOR_LM, -1, cv2.LINE_AA)

    # bone_vectors — 화면 좌표(landmarks)로 화살표
    for _bone_name, start, end in BONE_SEGMENTS:
        p1 = _resolve_lm_pixel(start, lms, w, h)
        p2 = _resolve_lm_pixel(end, lms, w, h)
        cv2.arrowedLine(out, p1, p2, COLOR_BONE, 2, tipLength=0.2, line_type=cv2.LINE_AA)

    joint_angles = frame_data.get("joint_angles", {})
    for angle_key, joint_name in ANGLE_LABEL_JOINTS.items():
        if angle_key not in joint_angles or joint_name not in lms:
            continue
        pt = _lm_pixel(lms[joint_name], w, h)
        label = f"{angle_key}: {joint_angles[angle_key]:.1f}"
        cv2.putText(
            out, label, (pt[0] + 8, pt[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_ANGLE, 1, cv2.LINE_AA,
        )

    idx = frame_data.get("frame_index", 0)
    t = frame_data.get("time_sec", 0.0)
    cv2.putText(
        out, f"frame {idx}  t={t:.2f}s", (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_TEXT, 2, cv2.LINE_AA,
    )
    return out


def _draw_normalized_mini(
    panel: np.ndarray,
    norm_lms: Dict[str, dict],
    ox: int,
    oy: int,
    pw: int,
    ph: int,
) -> None:
    """패널 안에 정규화 스켈레톤 2D 미니맵 (x,y 투영)."""
    xs = [p["x"] for p in norm_lms.values()]
    ys = [p["y"] for p in norm_lms.values()]
    if not xs:
        return
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 0.01)
    pad = 20
    scale = min((pw - 2 * pad) / span, (ph - 2 * pad) / span)

    def to_panel(name: str) -> Tuple[int, int]:
        if name == "mid_hip":
            nx = (norm_lms["left_hip"]["x"] + norm_lms["right_hip"]["x"]) / 2
            ny = (norm_lms["left_hip"]["y"] + norm_lms["right_hip"]["y"]) / 2
        elif name == "mid_shoulder":
            nx = (norm_lms["left_shoulder"]["x"] + norm_lms["right_shoulder"]["x"]) / 2
            ny = (norm_lms["left_shoulder"]["y"] + norm_lms["right_shoulder"]["y"]) / 2
        else:
            nx, ny = norm_lms[name]["x"], norm_lms[name]["y"]
        cx = ox + pw // 2
        cy = oy + ph // 2
        px = int(cx + (nx - (min_x + max_x) / 2) * scale)
        py = int(cy + (ny - (min_y + max_y) / 2) * scale)
        return px, py

    for _name, start, end in BONE_SEGMENTS:
        try:
            p1 = to_panel(start)
            p2 = to_panel(end)
        except KeyError:
            continue
        cv2.line(panel, p1, p2, COLOR_NORM, 2, cv2.LINE_AA)

    for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip", "nose"):
        if name in norm_lms:
            cv2.circle(panel, to_panel(name), 3, COLOR_NORM, -1, cv2.LINE_AA)


def _build_side_panel(frame_data: dict, panel_h: int) -> np.ndarray:
    panel = np.full((panel_h, PANEL_WIDTH, 3), COLOR_PANEL_BG, dtype=np.uint8)
    y = 28
    line_h = 22

    def put(line: str, color=COLOR_TEXT, scale=0.48) -> None:
        nonlocal y
        cv2.putText(
            panel, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
            scale, color, 1, cv2.LINE_AA,
        )
        y += line_h

    put("Analysis Panel", COLOR_LM, 0.55)
    y += 4
    put("--- joint_angles (deg) ---", (180, 180, 180), 0.42)
    for k, v in frame_data.get("joint_angles", {}).items():
        put(f"  {k}: {v:.1f}")

    y += 6
    put("--- bone_vectors ---", (180, 180, 180), 0.42)
    for k, v in frame_data.get("bone_vectors", {}).items():
        put(
            f"  {k}: ({v['x']:.2f},{v['y']:.2f},{v['z']:.2f})"
            f" L={v['magnitude']:.2f}",
            scale=0.38,
        )

    y += 6
    put("--- normalized (mini) ---", (180, 180, 180), 0.42)
    mini_h = min(220, panel_h - y - 20)
    if mini_h > 40:
        _draw_normalized_mini(
            panel,
            frame_data.get("normalized_landmarks", {}),
            0, y, PANEL_WIDTH, mini_h,
        )

    y = panel_h - 80
    put("--- landmarks (sample) ---", (180, 180, 180), 0.42)
    lms = frame_data.get("landmarks", {})
    for name in ("nose", "left_wrist", "right_wrist"):
        if name in lms:
            p = lms[name]
            put(
                f"  {name}: x={p['x']:.3f} y={p['y']:.3f}"
                f" z={p['z']:.3f}",
                scale=0.38,
            )

    return panel


def render_annotated_video(
    source_video_path: str,
    extraction_result: dict,
    output_filename: str,
) -> Path:
    """
    원본 영상 + 프레임별 분석 오버레이 → domain1/video_data/{output_filename}
  """
    ensure_video_data_dir()
    output_path = VIDEO_DATA_DIR / output_filename

    frames_data: List[dict] = extraction_result["frames"]
    fps = float(extraction_result.get("fps") or 30.0)

    cap = cv2.VideoCapture(source_video_path)
    if not cap.isOpened():
        raise ValueError(f"시각화용 영상을 열 수 없습니다: {source_video_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_w = w + PANEL_WIDTH
    out_h = h

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (out_w, out_h))
    if not writer.isOpened():
        cap.release()
        raise ValueError("annotated 영상 Writer를 열 수 없습니다 (코덱 mp4v)")

    for frame_data in frames_data:
        ret, frame = cap.read()
        if not ret:
            break
        vis = _draw_landmarks_overlay(frame, frame_data)
        panel = _build_side_panel(frame_data, out_h)
        combined = np.hstack([vis, panel])
        writer.write(combined)

    cap.release()
    writer.release()
    return output_path


def build_annotated_video_meta(filename: str) -> dict:
    """JSON 응답에 넣을 annotated_video 메타."""
    return {
        "filename": filename,
        "relative_path": f"domain/domain1/video_data/{filename}",
        "url": f"/video/data/{filename}",
    }
