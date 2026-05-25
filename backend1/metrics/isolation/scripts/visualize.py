"""
ref/user 분할 화면 시각화 — isolation 채점 확인용 (v5).

동기화 원칙
  채점 로직(_score_motion_segments) 이 실제로 비교한 프레임 쌍만 보여준다.
  beat k 의 대표 user_frame 과 ref_frame(= aligned_pairs 그룹 중간 pair) 을
  1 비트 길이만큼 나란히 표시 → ref·user 가 '완전히 동일한 순간' 비교.

렌더링 구조
  비트 k  → (user_rep_fi, ref_rep_fi) 를 beat_gap_frames 프레임 반복 출력
  비트 간 전환 시 0.12 s 의 "전환 플래시" 오버레이 삽입
  오디오: user 영상의 비교 구간 시작(time_sec 기준) ffmpeg 트림

품질
  ffmpeg 가 있으면 rawvideo 파이프 → H.264 직접 인코딩 (mp4v 중간본 없음)
  ffmpeg 없으면 cv2.VideoWriter(mp4v) 폴백 (화질 낮음)

오버레이
  헤더: fi / time_sec 텍스트 + 색상 지역 배지(TORSO/ARMS/LEGS)
  하단: Beat 카운터, Seg 정보, Score, 지역 배지, MATCH/MISMATCH 배너
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ─── 레이아웃 상수 ────────────────────────────────────────────────────
_HEADER_H = 95    # 헤더 오버레이 높이 (px)
_BOTTOM_H = 130   # 하단 패널 오버레이 높이 (px)

# ─── 색상 (BGR) ──────────────────────────────────────────────────────
_BLACK   = (0,   0,   0)
_WHITE   = (255, 255, 255)
_CYAN    = (255, 220,   0)
_TORSO_C = (255,  60,   0)
_ARMS_C  = (50,  200,   0)
_LEGS_C  = (0,   165, 255)
_NEUTRAL = (150, 150, 150)
_GREEN   = (0,   200,  60)
_RED     = (0,    50, 220)
_TEXT_C  = (240, 240, 240)
_PANEL_C = (20,   15,  40)
_FLASH_C = (180, 200,   0)

_REGION_COLOR: Dict[str, Tuple[int, int, int]] = {
    "torso": _TORSO_C,
    "arms":  _ARMS_C,
    "legs":  _LEGS_C,
}
_REGION_LABEL = {"torso": "TORSO", "arms": "ARMS", "legs": "LEGS"}

_SKELETON_EDGES = (
    ("left_shoulder",  "right_shoulder"),
    ("left_shoulder",  "left_elbow"),
    ("left_elbow",     "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow",    "right_wrist"),
    ("left_shoulder",  "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip",       "right_hip"),
    ("left_hip",       "left_knee"),
    ("left_knee",      "left_ankle"),
    ("right_hip",      "right_knee"),
    ("right_knee",     "right_ankle"),
)
_TORSO_SET = frozenset(["left_shoulder", "right_shoulder", "left_hip", "right_hip"])
_ARMS_SET  = frozenset(["left_elbow", "left_wrist", "right_elbow", "right_wrist"])
_LEGS_SET  = frozenset(["left_knee", "left_ankle", "right_knee", "right_ankle"])


def _edge_region(a: str, b: str) -> str:
    if a in _TORSO_SET and b in _TORSO_SET:
        return "torso"
    if a in _ARMS_SET or b in _ARMS_SET:
        return "arms"
    if a in _LEGS_SET or b in _LEGS_SET:
        return "legs"
    return "torso"


# ─── 그리기 유틸 ─────────────────────────────────────────────────────

def _resolve_ffmpeg() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _resize_panel(frame: np.ndarray, pw: int, ph: int) -> np.ndarray:
    import cv2
    if frame.shape[1] == pw and frame.shape[0] == ph:
        return frame
    return cv2.resize(frame, (pw, ph), interpolation=cv2.INTER_LANCZOS4)


def _txt(
    img: np.ndarray,
    text: str,
    pos: Tuple[int, int],
    color: Tuple[int, int, int],
    scale: float = 0.65,
    thick: int = 2,
) -> None:
    import cv2
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, _BLACK,  thick + 2, cv2.LINE_AA)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color,   thick,     cv2.LINE_AA)


def _panel_bg(img: np.ndarray, x: int, y: int, w: int, h: int, alpha: float = 0.62) -> None:
    import cv2
    ovl = img.copy()
    cv2.rectangle(ovl, (x, y), (x + w, y + h), _PANEL_C, -1)
    cv2.addWeighted(ovl, alpha, img, 1.0 - alpha, 0, img)


def _region_badge(
    img: np.ndarray,
    label: str,
    col: Tuple[int, int, int],
    x: int,
    y: int,
    w: int = 120,
    h: int = 30,
) -> None:
    """색상 채워진 지역 배지 (TORSO / ARMS / LEGS)."""
    import cv2
    cv2.rectangle(img, (x, y), (x + w, y + h), _BLACK, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), col,    -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), _WHITE,  1)
    scale = 0.62
    thick = 2
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    tx = x + max(4, (w - tw) // 2)
    ty = y + (h + th) // 2
    cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, _BLACK, thick + 2, cv2.LINE_AA)
    cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, _WHITE, thick,     cv2.LINE_AA)


def _stroke(img: np.ndarray, p1, p2, color, thick: int) -> None:
    import cv2
    cv2.line(img, p1, p2, _BLACK, thick + 3, cv2.LINE_AA)
    cv2.line(img, p1, p2, color,  thick,     cv2.LINE_AA)


def _dot(img: np.ndarray, center, radius: int, color) -> None:
    import cv2
    cv2.circle(img, center, radius + 2, _BLACK, -1, cv2.LINE_AA)
    cv2.circle(img, center, radius,     color,  -1, cv2.LINE_AA)
    cv2.circle(img, center, radius + 1, _WHITE,  1, cv2.LINE_AA)


def _draw_skeleton(
    img: np.ndarray,
    landmarks: Dict[str, dict],
    x0: int, y0: int, pw: int, ph: int,
    *,
    dominant_region: Optional[str],
    base_color: Tuple[int, int, int],
    joint_radius: int = 7,
) -> None:
    import cv2
    all_names = set(sum((list(e) for e in _SKELETON_EDGES), []))
    pts: Dict[str, Tuple[int, int]] = {}
    for name in all_names:
        lm = landmarks.get(name)
        if lm:
            vis = float(lm.get("visibility", 1.0))
            if vis < 0.3:
                continue
            px = int(x0 + float(lm["x"]) * pw)
            py = int(y0 + float(lm["y"]) * ph)
            if x0 <= px < x0 + pw and y0 <= py < y0 + ph:
                pts[name] = (px, py)

    for a, b in _SKELETON_EDGES:
        if a not in pts or b not in pts:
            continue
        if dominant_region:
            er    = _edge_region(a, b)
            col   = _REGION_COLOR.get(er, _NEUTRAL)
            thick = 7 if er == dominant_region else 3
        else:
            col, thick = base_color, 4
        _stroke(img, pts[a], pts[b], col, thick)

    jcol = _REGION_COLOR.get(dominant_region, base_color) if dominant_region else base_color
    for p in pts.values():
        _dot(img, p, joint_radius + (2 if dominant_region else 0), jcol)


# ─── ffmpeg 인코딩 유틸 ───────────────────────────────────────────────

_FFMPEG_ENCODER_CACHE: Dict[str, frozenset] = {}

_ENCODER_BY_DEVICE: Dict[str, str] = {
    "nvenc": "h264_nvenc",
    "amf":   "h264_amf",
    "qsv":   "h264_qsv",
    "cpu":   "libx264",
}

_NVENC_PRESET_MAP: Dict[str, str] = {
    "ultrafast": "p1",
    "fast": "p3",
    "medium": "p4",
    "slow": "p6",
    "veryslow": "p7",
}


def _ffmpeg_list_encoders(ffmpeg: str) -> frozenset:
    if ffmpeg in _FFMPEG_ENCODER_CACHE:
        return _FFMPEG_ENCODER_CACHE[ffmpeg]
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True, text=True, timeout=30,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    found: set = set()
    for token in ("h264_nvenc", "h264_amf", "h264_qsv", "libx264"):
        if token in blob:
            found.add(token)
    _FFMPEG_ENCODER_CACHE[ffmpeg] = frozenset(found)
    return _FFMPEG_ENCODER_CACHE[ffmpeg]


def _resolve_video_encoder(ffmpeg: str, encode_device: str) -> Tuple[str, str]:
    available = _ffmpeg_list_encoders(ffmpeg)
    if encode_device == "cpu":
        return "libx264", "cpu"
    if encode_device != "auto":
        enc_id = _ENCODER_BY_DEVICE.get(encode_device, "libx264")
        if enc_id in available:
            return enc_id, encode_device
        print(f"  요청 인코더 '{encode_device}'({enc_id}) 미지원 → libx264", flush=True)
        return "libx264", "cpu"
    for dev in ("nvenc", "amf", "qsv"):
        enc_id = _ENCODER_BY_DEVICE[dev]
        if enc_id in available:
            return enc_id, dev
    return "libx264", "cpu"


def _video_encode_args(encoder_id: str, crf: int, preset: str) -> List[str]:
    q = str(max(0, min(51, crf)))
    if encoder_id == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", _NVENC_PRESET_MAP.get(preset, "p4"),
                "-rc", "vbr", "-cq", q, "-b:v", "0"]
    if encoder_id == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced",
                "-rc", "cqp", "-qp_i", q, "-qp_p", q]
    if encoder_id == "h264_qsv":
        qsv_p = preset if preset in ("veryfast","faster","fast","medium","slow","slower","veryslow") else "medium"
        return ["-c:v", "h264_qsv", "-preset", qsv_p, "-global_quality", q]
    return ["-c:v", "libx264", "-crf", q, "-preset", preset]


def _open_ffmpeg_pipe(
    ffmpeg: str,
    output_path: Path,
    fps: float,
    width: int,
    height: int,
    *,
    crf: int,
    preset: str,
    encode_device: str,
) -> "subprocess.Popen[bytes]":
    """rawvideo stdin → H.264 파이프 인코딩 프로세스."""
    enc_id, enc_label = _resolve_video_encoder(ffmpeg, encode_device)
    print(f"  ffmpeg 파이프 인코딩: {enc_label}({enc_id}) crf={crf} preset={preset}", flush=True)
    cmd: List[str] = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", f"{fps:.3f}",
        "-i", "pipe:0",
        *_video_encode_args(enc_id, crf, preset),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


# ─── Beat 데이터 구축 ─────────────────────────────────────────────────

def _build_beat_data(
    pairs: List[Dict[str, Any]],
) -> Tuple[
    List[int],
    Dict[int, Dict[str, Any]],
    Dict[int, Dict[str, Any]],
]:
    """score.py 와 동일하게 정렬 후 _score_motion_segments 호출."""
    from metrics.isolation.score import _score_motion_segments

    sorted_pairs = sorted(pairs, key=lambda p: (p["user_frame"], p["ref_frame"]))

    beat_groups: Dict[int, list] = defaultdict(list)
    for p in sorted_pairs:
        bi = int(p.get("beat_index", -1))
        if bi >= 0:
            beat_groups[bi].append(p)

    beat_indices = sorted(beat_groups.keys())

    beat_to_rep: Dict[int, Dict[str, Any]] = {
        bi: beat_groups[bi][len(beat_groups[bi]) // 2]
        for bi in beat_indices
    }

    segments = _score_motion_segments(sorted_pairs)
    beat_to_seg: Dict[int, Dict[str, Any]] = {}
    for seg in segments:
        for bi in range(int(seg["beat_start"]), int(seg["beat_end"]) + 1):
            beat_to_seg[bi] = seg

    return beat_indices, beat_to_rep, beat_to_seg


# ─── 단일 비트 캔버스 합성 ────────────────────────────────────────────

def _compose_beat_canvas(
    u_frame: np.ndarray,
    r_frame: Optional[np.ndarray],
    u_pose: Optional[Dict[str, Any]],
    r_pose: Optional[Dict[str, Any]],
    beat_idx: int,
    beat_total: int,
    seg: Optional[Dict[str, Any]],
    pw: int,
    ph: int,
    *,
    flash: float = 0.0,
) -> np.ndarray:
    import cv2

    out_w = pw * 2
    canvas = np.zeros((ph, out_w, 3), dtype=np.uint8)

    # 비디오 패널 (LANCZOS4 리사이즈)
    canvas[:ph, :pw] = _resize_panel(r_frame, pw, ph) if r_frame is not None else 0
    canvas[:ph, pw:] = _resize_panel(u_frame, pw, ph)

    ref_region  = seg["ref_region"]       if seg else None
    user_region = seg.get("user_region")  if seg else None
    seg_score   = seg.get("score")        if seg else None
    reg_match   = seg.get("region_match") if seg else None

    ref_col  = _REGION_COLOR.get(ref_region,  _CYAN)   if ref_region  else _CYAN
    user_col = _REGION_COLOR.get(user_region, _TEXT_C) if user_region else _TEXT_C

    # 스켈레톤
    if r_pose and r_pose.get("landmarks"):
        _draw_skeleton(canvas, r_pose["landmarks"],  0, 0, pw, ph,
                       dominant_region=ref_region,  base_color=_CYAN,    joint_radius=7)
    if u_pose and u_pose.get("landmarks"):
        _draw_skeleton(canvas, u_pose["landmarks"], pw, 0, pw, ph,
                       dominant_region=user_region, base_color=_NEUTRAL, joint_radius=8)

    r_fi = int(r_pose["frame_index"]) if r_pose else -1
    u_fi = int(u_pose["frame_index"]) if u_pose else -1
    r_t  = float(r_pose["time_sec"])  if r_pose else 0.0
    u_t  = float(u_pose["time_sec"])  if u_pose else 0.0

    # ── 헤더 오버레이 ──────────────────────────────────────────────────
    _panel_bg(canvas,  0, 0, pw, _HEADER_H)
    _panel_bg(canvas, pw, 0, pw, _HEADER_H)

    # 텍스트 행 (fi / time)
    _txt(canvas, f"REF   fi={r_fi}   t={r_t:.2f}s",  (10, 30), ref_col,  scale=0.65, thick=2)
    _txt(canvas, f"USER  fi={u_fi}   t={u_t:.2f}s", (pw + 10, 30), user_col, scale=0.65, thick=2)

    # 지역 배지 (헤더 하단)
    ref_lbl  = _REGION_LABEL.get(ref_region,  "---") if ref_region  else "---"
    user_lbl = _REGION_LABEL.get(user_region, "---") if user_region else "---"
    badge_w, badge_h = 115, 30
    _region_badge(canvas, ref_lbl,  ref_col,   pw // 2 - badge_w // 2, 56, badge_w, badge_h)
    _region_badge(canvas, user_lbl, user_col,  pw + pw // 2 - badge_w // 2, 56, badge_w, badge_h)

    # 헤더 구분선
    cv2.line(canvas, (0, _HEADER_H - 1), (out_w, _HEADER_H - 1), _WHITE, 1)

    # ── 하단 패널 오버레이 ──────────────────────────────────────────────
    bot_y = ph - _BOTTOM_H
    _panel_bg(canvas, 0, bot_y, out_w, _BOTTOM_H, alpha=0.72)

    # Row 1: Beat 카운터 | Seg | Score
    seg_str   = f"Seg [{seg['beat_start']}~{seg['beat_end']}]" if seg else "---"
    score_str = f"Score {seg_score:.1f}" if seg_score is not None else "Score ---"
    _txt(canvas, f"Beat {beat_idx} / {beat_total}",
         (12, bot_y + 32), _TEXT_C, scale=0.72, thick=2)
    _txt(canvas, seg_str,
         (pw - 5, bot_y + 32), _TEXT_C, scale=0.62)
    _txt(canvas, score_str,
         (pw + 12, bot_y + 32), _CYAN, scale=0.68, thick=2)

    # Row 2: 지역 배지 (REF / USER)
    badge2_w, badge2_h = 140, 32
    _region_badge(canvas, f"REF: {ref_lbl}",
                  ref_col,  pw // 2 - badge2_w // 2,      bot_y + 52, badge2_w, badge2_h)
    _region_badge(canvas, f"USER: {user_lbl}",
                  user_col, pw + pw // 2 - badge2_w // 2, bot_y + 52, badge2_w, badge2_h)

    # Row 3: MATCH / MISMATCH 배너 (전체 폭, 색상 채워짐)
    if reg_match is not None:
        m_col  = _GREEN if reg_match else _RED
        m_text = "MATCH" if reg_match else "MISMATCH"
        bar_y1 = bot_y + _BOTTOM_H - 42
        bar_y2 = bot_y + _BOTTOM_H - 5
        bar_h  = bar_y2 - bar_y1
        cv2.rectangle(canvas, (5,       bar_y1), (out_w - 5, bar_y2), m_col,  -1)
        cv2.rectangle(canvas, (5,       bar_y1), (out_w - 5, bar_y2), _WHITE,  1)
        scale = 0.82
        thick = 2
        (tw, th), _ = cv2.getTextSize(m_text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        tx = (out_w - tw) // 2
        ty = bar_y1 + (bar_h + th) // 2
        cv2.putText(canvas, m_text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, _BLACK, thick + 3, cv2.LINE_AA)
        cv2.putText(canvas, m_text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, _WHITE, thick,     cv2.LINE_AA)

    # 중앙 구분선
    cv2.line(canvas, (pw, 0), (pw, ph), _WHITE, 2, cv2.LINE_AA)

    # 비트 전환 플래시 (외곽 테두리)
    if flash > 0.02:
        border    = max(3, int(8 * flash))
        flash_col = tuple(int(c * flash) for c in _FLASH_C)
        cv2.rectangle(canvas, (0,  0), (pw - 1,      ph - 1), flash_col, border)
        cv2.rectangle(canvas, (pw, 0), (out_w - 1,   ph - 1), flash_col, border)

    return canvas


# ─── 메인 렌더러 ──────────────────────────────────────────────────────

def render_isolation_split(
    ref_video: str | Path,
    user_video: str | Path,
    ref_json_path: str | Path,
    user_json_path: str | Path,
    output_path: str | Path,
    *,
    aligned_pairs_path: Optional[str | Path] = None,
    panel_width: Optional[int] = None,
    crf: int = 17,
    encode_preset: str = "medium",
    encode_device: str = "auto",
) -> Path:
    """
    비트 단위 분할 화면 영상.

    채점에 사용된 (user_rep, ref_rep) 대표 프레임 쌍을
    1 비트 길이만큼 나란히 보여 주고 비트마다 전환.
    ffmpeg 가 있으면 rawvideo → H.264 직접 파이프 (mp4v 중간본 없음).
    """
    import cv2

    # ── 1. JSON 로드 ──────────────────────────────────────────────────
    ref_data  = json.loads(Path(ref_json_path).read_text(encoding="utf-8"))
    user_data = json.loads(Path(user_json_path).read_text(encoding="utf-8"))

    fps = float(ref_data.get("fps", 30.0))

    ref_by_fi:  Dict[int, Dict] = {int(f["frame_index"]): f for f in ref_data["frames"]}
    user_by_fi: Dict[int, Dict] = {int(f["frame_index"]): f for f in user_data["frames"]}

    # ── 2. aligned_pairs ─────────────────────────────────────────────
    if aligned_pairs_path and Path(aligned_pairs_path).is_file():
        aligned = json.loads(Path(aligned_pairs_path).read_text(encoding="utf-8"))
    else:
        from metrics.isolation.align import align_from_paths
        print("  aligned_pairs.json 없음 → 자동 정렬 중...", flush=True)
        aligned = align_from_paths(str(user_json_path), str(ref_json_path), method="beat")

    pairs      = aligned.get("pairs") or []
    align_meta = aligned.get("alignment") or {}

    if not pairs:
        raise ValueError("정렬 pair 없음. align 먼저 실행하세요.")

    bpm = float(align_meta.get("ref_bpm") or 120.0)
    print(
        f"  pairs={len(pairs)}  bpm={bpm}  "
        f"beat_lag={align_meta.get('beat_lag_sec','?')}s",
        flush=True,
    )

    # ── 3. Beat 데이터 ────────────────────────────────────────────────
    beat_indices, beat_to_rep, beat_to_seg = _build_beat_data(pairs)

    first_rep = beat_to_rep[beat_indices[0]]
    user_audio_start_sec = float(first_rep["user"]["time_sec"])

    n_segs = len({s["beat_start"] for s in beat_to_seg.values()})
    print(f"  beats={len(beat_indices)}  motion_segments={n_segs}", flush=True)

    beat_total = len(beat_indices)

    # ── 4. 비트 길이(프레임 수) ───────────────────────────────────────
    beat_gap_frames = max(4, round(fps * 60.0 / bpm))
    flash_frames    = max(1, round(fps * 0.12))
    print(f"  beat_gap_frames={beat_gap_frames}  flash_frames={flash_frames}", flush=True)

    # ── 5. 영상 열기 ─────────────────────────────────────────────────
    cap_user = cv2.VideoCapture(str(user_video))
    cap_ref  = cv2.VideoCapture(str(ref_video))
    if not cap_user.isOpened():
        raise ValueError(f"user 영상 열기 실패: {user_video}")
    if not cap_ref.isOpened():
        raise ValueError(f"ref 영상 열기 실패: {ref_video}")

    u_w = int(cap_user.get(cv2.CAP_PROP_FRAME_WIDTH))
    u_h = int(cap_user.get(cv2.CAP_PROP_FRAME_HEIGHT))
    r_w = int(cap_ref.get(cv2.CAP_PROP_FRAME_WIDTH))
    pw  = panel_width or max(u_w, r_w)
    ph  = u_h

    out    = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_suffix(".silent.mp4")

    # ── 6. 비디오 라이터 (ffmpeg 파이프 우선, cv2 폴백) ──────────────
    ffmpeg     = _resolve_ffmpeg()
    pipe_proc  = None
    writer_cv2 = None

    if ffmpeg:
        try:
            pipe_proc = _open_ffmpeg_pipe(
                ffmpeg, silent, fps, pw * 2, ph,
                crf=crf, preset=encode_preset, encode_device=encode_device,
            )
        except Exception as e:
            print(f"  ffmpeg 파이프 열기 실패: {e} → cv2.VideoWriter 폴백", flush=True)
            pipe_proc = None

    if pipe_proc is None:
        print("  cv2.VideoWriter(mp4v) 사용 (ffmpeg 없거나 파이프 실패)", flush=True)
        fourcc     = cv2.VideoWriter_fourcc(*"mp4v")
        writer_cv2 = cv2.VideoWriter(str(silent), fourcc, fps, (pw * 2, ph))

    # ── 7. 비트별 렌더링 ─────────────────────────────────────────────
    cached_user_fi = -1
    cached_ref_fi  = -1
    cached_u_frame: Optional[np.ndarray] = None
    cached_r_frame: Optional[np.ndarray] = None

    def _write(canvas: np.ndarray) -> None:
        if pipe_proc is not None:
            pipe_proc.stdin.write(canvas.tobytes())
        else:
            writer_cv2.write(canvas)

    for beat_idx in beat_indices:
        rep  = beat_to_rep[beat_idx]
        u_fi = int(rep["user_frame"])
        r_fi = int(rep["ref_frame"])

        if u_fi != cached_user_fi:
            cap_user.set(cv2.CAP_PROP_POS_FRAMES, float(u_fi))
            ret_u, frm_u = cap_user.read()
            if ret_u:
                cached_u_frame = frm_u
                cached_user_fi = u_fi

        if r_fi != cached_ref_fi:
            cap_ref.set(cv2.CAP_PROP_POS_FRAMES, float(r_fi))
            ret_r, frm_r = cap_ref.read()
            if ret_r:
                cached_r_frame = frm_r
                cached_ref_fi  = r_fi

        u_pose = user_by_fi.get(u_fi)
        r_pose = ref_by_fi.get(r_fi)
        seg    = beat_to_seg.get(beat_idx)

        for fi in range(flash_frames):
            strength = 1.0 - fi / max(flash_frames, 1)
            _write(_compose_beat_canvas(
                cached_u_frame, cached_r_frame,
                u_pose, r_pose,
                beat_idx, beat_total, seg, pw, ph,
                flash=strength,
            ))

        still_frames  = max(1, beat_gap_frames - flash_frames)
        canvas_still  = _compose_beat_canvas(
            cached_u_frame, cached_r_frame,
            u_pose, r_pose,
            beat_idx, beat_total, seg, pw, ph,
            flash=0.0,
        )
        for _ in range(still_frames):
            _write(canvas_still)

    cap_user.release()
    cap_ref.release()

    if pipe_proc is not None:
        pipe_proc.stdin.close()
        pipe_proc.wait()
        if pipe_proc.returncode != 0:
            err_bytes = pipe_proc.stderr.read() if pipe_proc.stderr else b""
            err = err_bytes.decode("utf-8", errors="replace")[-400:]
            print(f"  ffmpeg 파이프 인코딩 오류 (returncode={pipe_proc.returncode}): {err}", flush=True)
    else:
        writer_cv2.release()

    video_src = silent

    # ── 8. 오디오 합성 ────────────────────────────────────────────────
    if ffmpeg:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            cmd = [
                ffmpeg, "-y",
                "-i", str(video_src),
                "-ss", str(user_audio_start_sec),
                "-i", str(user_video),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-map", "0:v:0",
                "-map", "1:a:0?",
                "-shortest",
                str(tmp_path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                shutil.copy2(tmp_path, out)
            else:
                print(f"  ffmpeg 오디오 합성 오류: {proc.stderr[-200:]}", flush=True)
                shutil.copy2(video_src, out)
        finally:
            if video_src.exists() and video_src != out:
                video_src.unlink(missing_ok=True)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    else:
        print("  ffmpeg 없음 — 오디오 없이 저장", flush=True)
        shutil.copy2(video_src, out)
        if video_src.exists() and video_src != out:
            video_src.unlink(missing_ok=True)

    return out
