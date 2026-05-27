"""
분할 화면 비교 결과 영상 — 패널당 스켈레톤 1개 오버레이.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .joint_live_viz import DISPLAY_JOINTS

_SKELETON_EDGES = (
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)

_DEFAULT_LEFT_LABEL = "Reference"
_DEFAULT_RIGHT_LABEL = "Compare"
# BGR — 화면 왼쪽=파란, 오른쪽=빨강, 매칭 구간=노랑
_COLOR_PANEL_LEFT = (255, 0, 0)
_COLOR_PANEL_RIGHT = (0, 0, 255)
_COLOR_MATCHED = (0, 255, 255)
_LINE_THICKNESS = 2
_JOINT_RADIUS = 3
_SPLIT_LINE = (200, 200, 200)


def _resolve_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _attach_audio(silent_path: Path, source_video: str, out_path: Path) -> None:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        shutil.copy2(silent_path, out_path)
        return
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(silent_path),
        "-i",
        str(source_video),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.copy2(silent_path, out_path)


def _motion_from_analysis(analysis: dict[str, Any]) -> dict[str, Any] | None:
    motion = analysis.get("motion")
    if motion:
        return motion
    creativity = analysis.get("creativity") or {}
    return creativity.get("motion")


def _matched_ref_intervals(analysis: dict[str, Any]) -> list[tuple[float, float]]:
    """양끝 경계가 user와 매칭된 ref 구간 [start, end] (초)."""
    motion = _motion_from_analysis(analysis)
    if not motion:
        return []
    out: list[tuple[float, float]] = []
    for seg in motion.get("segments") or []:
        if seg.get("skipped"):
            continue
        if not (seg.get("start_matched") and seg.get("end_matched")):
            continue
        rw = seg.get("ref_window_sec") or []
        if len(rw) >= 2:
            out.append((float(rw[0]), float(rw[1])))
    return out


def _time_in_matched_intervals(
    t: float, intervals: list[tuple[float, float]], *, margin_sec: float = 0.02
) -> bool:
    for lo, hi in intervals:
        if lo - margin_sec <= t <= hi + margin_sec:
            return True
    return False


def _frame_time_sec(
    user_fr: dict[str, Any] | None,
    ref_fr: dict[str, Any] | None,
    frame_index: int,
    fps: float,
) -> float:
    for fr in (user_fr, ref_fr):
        if fr and fr.get("time_sec") is not None:
            return float(fr["time_sec"])
    return float(frame_index) / fps if fps > 0 else float(frame_index)


def _frames_by_source(frames: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for fr in frames:
        src = int(fr.get("source_frame_index", fr.get("frame_index", 0)))
        out[src] = fr
    return out


def _panel_region(
    panel: str,
    split_x: int,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int, int, int]:
    """물리 패널(left|right) → (x0, y0, pw, ph). landmarks는 해당 crop 기준 0~1."""
    if panel == "left":
        return 0, 0, split_x, frame_h
    return split_x, 0, frame_w - split_x, frame_h


def _detection_region(
    x0: int,
    y0: int,
    pw: int,
    ph: int,
    center_crop_ratio: float | None,
) -> tuple[int, int, int, int]:
    """패널 내 포즈 검출에 쓴 영역 (중앙 crop 포함) → (x0, y0, w, h)."""
    if center_crop_ratio is None or not (0.0 < center_crop_ratio < 1.0):
        return x0, y0, pw, ph
    cw = max(32, int(pw * center_crop_ratio))
    ch = max(32, int(ph * center_crop_ratio))
    return x0 + (pw - cw) // 2, y0 + (ph - ch) // 2, cw, ch


def _landmark_px(
    lm: dict[str, float],
    x0: int,
    y0: int,
    pw: int,
    ph: int,
    *,
    center_crop_ratio: float | None = None,
) -> tuple[int, int] | None:
    # MediaPipe: x,y ∈ [0,1] — 검출에 넣은 이미지(패널 또는 패널 내 중앙 crop) 기준
    dx, dy, dw, dh = _detection_region(x0, y0, pw, ph, center_crop_ratio)
    px = int(dx + float(lm["x"]) * dw)
    py = int(dy + float(lm["y"]) * dh)
    return px, py


def _collect_points(
    landmarks: dict[str, dict],
    x0: int,
    y0: int,
    pw: int,
    ph: int,
    img_w: int,
    img_h: int,
    *,
    center_crop_ratio: float | None = None,
) -> dict[str, tuple[int, int]]:
    pts: dict[str, tuple[int, int]] = {}
    for name, _ in DISPLAY_JOINTS:
        lm = landmarks.get(name)
        if not lm or float(lm.get("visibility", 1)) < 0.35:
            continue
        p = _landmark_px(
            lm, x0, y0, pw, ph, center_crop_ratio=center_crop_ratio
        )
        if p and 0 <= p[0] < img_w and 0 <= p[1] < img_h:
            pts[name] = p
    return pts


def _draw_skeleton(
    img: np.ndarray,
    landmarks: dict[str, dict],
    x0: int,
    y0: int,
    pw: int,
    ph: int,
    color: tuple[int, int, int],
    *,
    center_crop_ratio: float | None = None,
) -> None:
    """패널 위 사람 1명 — 단색 선·작은 관절점만 (테두리·점수 없음)."""
    import cv2

    h, w = img.shape[:2]
    pts = _collect_points(
        landmarks, x0, y0, pw, ph, w, h, center_crop_ratio=center_crop_ratio
    )

    for a, b in _SKELETON_EDGES:
        if a in pts and b in pts:
            cv2.line(img, pts[a], pts[b], color, _LINE_THICKNESS, cv2.LINE_AA)
    for p in pts.values():
        cv2.circle(img, p, _JOINT_RADIUS, color, -1, cv2.LINE_AA)


def _draw_label(
    img: np.ndarray,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
) -> None:
    import cv2

    cv2.putText(
        img,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        1,
        cv2.LINE_AA,
    )


def render_split_screen_video(
    video_path: str,
    user_raw: dict[str, Any],
    ref_raw: dict[str, Any],
    analysis: dict[str, Any],
    output_path: str | Path,
    *,
    split_meta: dict[str, Any],
    left_label: str = _DEFAULT_LEFT_LABEL,
    right_label: str = _DEFAULT_RIGHT_LABEL,
) -> Path:
    """
    물리 좌/우 패널 각각 — 추출 crop 좌표에 맞춰 스켈레톤 오버레이.
    기본: 왼쪽=파란, 오른쪽=빨강. 양끝 매칭된 ref 구간에서는 양쪽 모두 노랑.
    """
    import cv2

    matched_intervals = _matched_ref_intervals(analysis)

    path = Path(video_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    left_tag = (left_label or _DEFAULT_LEFT_LABEL).strip() or _DEFAULT_LEFT_LABEL
    right_tag = (right_label or _DEFAULT_RIGHT_LABEL).strip() or _DEFAULT_RIGHT_LABEL
    # OpenCV 기본 폰트는 ASCII만 안정적 — 한글 등은 깨지므로 ASCII 기본값 사용
    if not left_tag.isascii():
        left_tag = _DEFAULT_LEFT_LABEL
    if not right_tag.isascii():
        right_tag = _DEFAULT_RIGHT_LABEL

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    split_x = int(split_meta.get("split_x_px", int(w * split_meta.get("split_ratio", 0.5))))

    ref_by_src = _frames_by_source(ref_raw.get("frames") or [])
    user_by_src = _frames_by_source(user_raw.get("frames") or [])
    user_panel = str(split_meta.get("user_panel", "left"))
    ref_panel = str(split_meta.get("reference_panel", "right"))
    center_crop_ratio: float | None = None
    if split_meta.get("center_crop_per_panel"):
        center_crop_ratio = float(split_meta.get("center_crop_ratio") or 0.72)

    silent = out.with_suffix(".silent.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(silent), fourcc, fps, (w, h))

    fi = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        def _draw_on_panel(
            fr: dict[str, Any] | None,
            panel: str,
            label: str,
            color: tuple[int, int, int],
        ) -> None:
            if not fr:
                return
            x0, y0, pw, ph = _panel_region(panel, split_x, w, h)
            _draw_skeleton(
                frame,
                fr.get("landmarks") or {},
                x0,
                y0,
                pw,
                ph,
                color,
                center_crop_ratio=center_crop_ratio,
            )
            _draw_label(frame, x0 + 10, 28, label, color)

        user_fr = user_by_src.get(fi)
        ref_fr = ref_by_src.get(fi)
        t_sec = _frame_time_sec(user_fr, ref_fr, fi, fps)
        in_matched = _time_in_matched_intervals(t_sec, matched_intervals)

        # crop 패널 좌표(0~1) → 해당 물리 패널에 오버레이 (옆 패널에 그리지 않음)
        for panel, default_color, tag in (
            ("left", _COLOR_PANEL_LEFT, left_tag),
            ("right", _COLOR_PANEL_RIGHT, right_tag),
        ):
            color = _COLOR_MATCHED if in_matched else default_color
            if user_panel == panel:
                _draw_on_panel(user_fr, panel, tag, color)
            elif ref_panel == panel:
                _draw_on_panel(ref_fr, panel, tag, color)

        cv2.line(frame, (split_x, 0), (split_x, h), _SPLIT_LINE, 1, cv2.LINE_AA)
        writer.write(frame)
        fi += 1

    cap.release()
    writer.release()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        _attach_audio(silent, str(path), tmp_path)
        shutil.copy2(tmp_path, out)
    finally:
        if silent.exists():
            silent.unlink()
        if tmp_path.exists():
            tmp_path.unlink()

    return out
