# -*- coding: utf-8 -*-
"""
compare_speed_video.py
======================
Side-by-side Before/After algorithm speed comparison video.

  Left  — BEFORE CODE OPTIMIZATION (SLOW)
           Loop-based per-joint scoring; all 17 joints always evaluated;
           no face-direction guard; no early-exit.

  Right — AFTER CODE OPTIMIZATION (FAST)
           Vectorised numpy scoring; face-direction guard; structural-joint
           early-exit when similarity is clearly below threshold.

Visual style matches EXACTLY:
  C:\\Users\\biop9\\dance_similarity\\output\\joint_scores_video.mp4

  - COLOR_A (230, 190, 30)  warm-yellow  — Dancer A skeleton
  - COLOR_B  (30, 120, 255) vivid-orange  — Dancer B skeleton
  - Score dots  GREEN ≥80%  YELLOW 60-79%  RED <60%
  - Per-joint % label + joint-name subtitle at every joint
  - Thin connecting line between matched joint pairs
  - 70 px bottom score bar with coloured fill + legend swatches

Data source
-----------
  C:\\Users\\biop9\\dance_similarity\\data\\duet.mp4
  C:\\Users\\biop9\\dance_similarity\\data\\.cache_duet.npz

Usage
-----
  cd C:\\Users\\biop9\\StudioProjects\\FOMnew\\backend1
  python -m metrics.accuracy.compare_speed_video

  Output: output/compare_speed_video.mp4
"""

import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Data source (dance_similarity project)
# ---------------------------------------------------------------------------
_DS_ROOT   = Path(r"C:\Users\biop9\dance_similarity")
_VIDEO     = _DS_ROOT / "data" / "duet.mp4"
_CACHE     = _DS_ROOT / "data" / ".cache_duet.npz"
_OUT_VIDEO = Path("output") / "compare_speed_video.mp4"

# ---------------------------------------------------------------------------
# Constants — matching joint_scores_video.mp4 exactly
# ---------------------------------------------------------------------------
JOINT_NAMES = [
    "nose", "L.eye", "R.eye", "L.ear", "R.ear",
    "L.shl", "R.shl", "L.elb", "R.elb",
    "L.wri", "R.wri", "L.hip", "R.hip",
    "L.kne", "R.kne", "L.ank", "R.ank",
]

# COCO-17 skeleton edges
COCO17_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

# Per-dancer skeleton colors (BGR) — identical to reference project
COLOR_A = (230, 190,  30)   # warm yellow  – Dancer A
COLOR_B = ( 30, 120, 255)   # vivid orange – Dancer B

C_BLACK = (0,   0,   0)
C_WHITE = (255, 255, 255)
C_GRAY  = (180, 180, 180)
FONT    = cv2.FONT_HERSHEY_SIMPLEX

# Scoring parameters
JOINT_TOLERANCE = 0.30
FACE_VIS_GATE   = 0.30
FACE_INDICES    = frozenset({0, 1, 2, 3, 4})
STRUCT_JOINTS   = [5, 6, 11, 12]
SIM_THRESHOLD   = 0.65


# ---------------------------------------------------------------------------
# Score → colour (BGR) — identical to reference project
# ---------------------------------------------------------------------------
def _score_bgr(score: float) -> tuple:
    if score >= 0.80:
        return (50, 210,  60)   # green
    elif score >= 0.60:
        return ( 0, 200, 230)   # yellow
    else:
        return (50,  60, 230)   # red


# ---------------------------------------------------------------------------
# Pose normalisation — copied from dance_similarity/src/aihub_loader.py
# ---------------------------------------------------------------------------
def _normalize(kps: np.ndarray) -> np.ndarray:
    out     = kps.copy()
    visible = kps[:, 2] > 0
    if visible[11] and visible[12]:
        hip = (kps[11, :2] + kps[12, :2]) / 2.0
    elif visible[11]:
        hip = kps[11, :2]
    elif visible[12]:
        hip = kps[12, :2]
    else:
        return out
    if visible[5] and visible[6]:
        shl = (kps[5, :2] + kps[6, :2]) / 2.0
    elif visible[5]:
        shl = kps[5, :2]
    elif visible[6]:
        shl = kps[6, :2]
    else:
        return out
    torso = np.linalg.norm(shl - hip)
    if torso < 1e-6:
        return out
    out[:, :2] = (kps[:, :2] - hip) / torso
    out[~visible, :2] = 0.0
    return out


# ---------------------------------------------------------------------------
# SLOW scoring — Before (original loop, no face guard, no early-exit)
# ---------------------------------------------------------------------------
def _score_slow(pa: np.ndarray, pb: np.ndarray):
    """
    Original loop-based per-joint scoring.
    Returns (scores_17, elapsed_ms)
    """
    na     = _normalize(pa)
    nb     = _normalize(pb)
    scores = np.full(17, np.nan, dtype=np.float32)
    denom  = 2.0 * JOINT_TOLERANCE ** 2

    t0 = time.perf_counter()
    for i in range(17):
        if na[i, 2] > 0.1 and nb[i, 2] > 0.1:
            d2 = float(((na[i, :2] - nb[i, :2]) ** 2).sum())
            scores[i] = np.exp(-d2 / denom)
    elapsed = (time.perf_counter() - t0) * 1_000.0

    return scores, elapsed


# ---------------------------------------------------------------------------
# FAST scoring — After (vectorised + face guard + early-exit)
# ---------------------------------------------------------------------------
def _face_dir(kps: np.ndarray) -> str:
    l_ok = float(kps[3, 2]) > FACE_VIS_GATE
    r_ok = float(kps[4, 2]) > FACE_VIS_GATE
    if l_ok and r_ok:
        return "front"
    if not l_ok and not r_ok:
        return "back"
    return "side"


def _score_fast(pa: np.ndarray, pb: np.ndarray):
    """
    Vectorised per-joint scoring with face-direction guard + early-exit.
    Returns (scores_17, elapsed_ms, face_dir_label, early_exit_fired)
    """
    na     = _normalize(pa)
    nb     = _normalize(pb)
    scores = np.full(17, np.nan, dtype=np.float32)
    denom  = 2.0 * JOINT_TOLERANCE ** 2

    t0 = time.perf_counter()

    dir_a = _face_dir(na)
    dir_b = _face_dir(nb)
    face_occluded  = (dir_a != "front") or (dir_b != "front")
    face_dir_label = dir_b

    valid = (na[:, 2] > 0.1) & (nb[:, 2] > 0.1)
    if face_occluded:
        for fi in FACE_INDICES:
            valid[fi] = False

    struct = np.zeros(17, dtype=bool)
    for si in STRUCT_JOINTS:
        if valid[si]:
            struct[si] = True

    early_exit = False
    if struct.any():
        d2_s   = ((na[struct, :2] - nb[struct, :2]) ** 2).sum(axis=1)
        coarse = float(np.mean(np.exp(-d2_s / denom)))
        if coarse < SIM_THRESHOLD / 2:
            scores[struct] = np.exp(-d2_s / denom)
            early_exit = True
            elapsed = (time.perf_counter() - t0) * 1_000.0
            return scores, elapsed, face_dir_label, True

    if valid.any():
        d2 = ((na[valid, :2] - nb[valid, :2]) ** 2).sum(axis=1)
        scores[valid] = np.exp(-d2 / denom)

    elapsed = (time.perf_counter() - t0) * 1_000.0
    return scores, elapsed, face_dir_label, False


# ---------------------------------------------------------------------------
# Drawing — exact visual match to joint_scores_video.mp4
# ---------------------------------------------------------------------------
def _draw_bones(img: np.ndarray, kps: np.ndarray, color: tuple) -> None:
    h, w = img.shape[:2]
    vis  = {i: (int(kps[i, 0]), int(kps[i, 1]))
            for i in range(17)
            if kps[i, 2] > 0.1 and 0 <= kps[i, 0] < w and 0 <= kps[i, 1] < h}
    for a, b in COCO17_EDGES:
        if a in vis and b in vis:
            cv2.line(img, vis[a], vis[b], color, 2, cv2.LINE_AA)


def _annotate(img: np.ndarray, pa: np.ndarray, pb: np.ndarray,
              joint_scores: np.ndarray, font_scale: float, dot_r: int) -> None:
    """
    Exact copy of _annotate() from dance_similarity/render_joint_scores.py.

      1. Bone connections (both dancers, in dancer colors)
      2. Score-coloured connecting line A→B for each matched joint
      3. Score-coloured dot at each joint (with dark border)
      4. Score "87%" percentage label (with dark outline)
      5. Tiny joint-name label below each dot (white)
    """
    h, w       = img.shape[:2]
    name_scale = max(0.28, font_scale * 0.55)

    # 1. Bones underneath everything
    _draw_bones(img, pa, COLOR_A)
    _draw_bones(img, pb, COLOR_B)

    # 2-5. Per-joint overlay
    for i in range(17):
        vis_a = pa[i, 2] > 0.1 and 0 <= pa[i, 0] < w and 0 <= pa[i, 1] < h
        vis_b = pb[i, 2] > 0.1 and 0 <= pb[i, 0] < w and 0 <= pb[i, 1] < h
        score = joint_scores[i]
        both  = vis_a and vis_b and not np.isnan(score)

        if both:
            ax, ay = int(pa[i, 0]), int(pa[i, 1])
            bx, by = int(pb[i, 0]), int(pb[i, 1])
            color  = _score_bgr(float(score))
            pct    = f"{int(score * 100)}%"

            # Score-coloured joint dots (drawn over bones)
            for cx, cy in [(ax, ay), (bx, by)]:
                cv2.circle(img, (cx, cy), dot_r + 1, C_BLACK, -1, cv2.LINE_AA)
                cv2.circle(img, (cx, cy), dot_r,     color,   -1, cv2.LINE_AA)

            # Score percentage label at each joint
            for cx, cy in [(ax, ay), (bx, by)]:
                tx = min(cx + dot_r + 3, w - 38)
                ty = max(cy - dot_r - 3, 14)
                cv2.putText(img, pct, (tx, ty), FONT, font_scale, C_BLACK, 3, cv2.LINE_AA)
                cv2.putText(img, pct, (tx, ty), FONT, font_scale, color,   1, cv2.LINE_AA)

            # Tiny joint-name below each dot
            name = JOINT_NAMES[i]
            for cx, cy in [(ax, ay), (bx, by)]:
                nx = max(cx - 14, 2)
                ny = min(cy + dot_r + 12, h - 2)
                cv2.putText(img, name, (nx, ny), FONT, name_scale,
                            C_BLACK,         2, cv2.LINE_AA)
                cv2.putText(img, name, (nx, ny), FONT, name_scale,
                            (240, 240, 240), 1, cv2.LINE_AA)

        else:
            # One or neither dancer visible — plain dot in dancer color
            if vis_a:
                cv2.circle(img, (int(pa[i, 0]), int(pa[i, 1])), dot_r, COLOR_A, -1, cv2.LINE_AA)
            if vis_b:
                cv2.circle(img, (int(pb[i, 0]), int(pb[i, 1])), dot_r, COLOR_B, -1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Header bar
# ---------------------------------------------------------------------------
def _make_header(w: int, h_px: int, title: str, theme_color: tuple) -> np.ndarray:
    hdr     = np.zeros((h_px, w, 3), np.uint8)
    hdr[:]  = (15, 15, 15)
    cv2.line(hdr, (0, h_px - 2), (w, h_px - 2), theme_color, 2)
    (tw, _), _ = cv2.getTextSize(title, FONT, 0.60, 2)
    tx = max((w - tw) // 2, 8)
    ty = h_px - 7
    cv2.putText(hdr, title, (tx + 1, ty + 1), FONT, 0.60, C_BLACK,     3, cv2.LINE_AA)
    cv2.putText(hdr, title, (tx,     ty),     FONT, 0.60, theme_color, 2, cv2.LINE_AA)
    return hdr


# ---------------------------------------------------------------------------
# Bottom score bar — matches reference joint_scores_video.mp4 layout
# ---------------------------------------------------------------------------
def _make_bar(vid_w: int, bar_h: int, overall: float, frame_idx: int,
              sync_prefix: str, theme_color: tuple,
              algo_line: str = "", speed_line: str = "") -> np.ndarray:

    S_GREEN  = _score_bgr(0.90)
    S_YELLOW = _score_bgr(0.70)
    S_RED    = _score_bgr(0.40)

    bar  = np.zeros((bar_h, vid_w, 3), np.uint8)

    # Coloured fill proportional to overall score (reference style)
    fill = max(int(overall * vid_w), 0)
    if fill > 0:
        bar[:, :fill] = _score_bgr(overall)

    # Accent line at top in theme color
    bar[:3, :] = theme_color

    # Algo/speed lines (top two text rows)
    if algo_line:
        cv2.putText(bar, algo_line,  (10, 16), FONT, 0.35, (190, 190, 190), 1, cv2.LINE_AA)
    if speed_line:
        # White outline first so black text is readable over any fill color
        cv2.putText(bar, speed_line, (10, 32), FONT, 0.38, C_WHITE, 3, cv2.LINE_AA)
        cv2.putText(bar, speed_line, (10, 32), FONT, 0.38, C_BLACK, 1, cv2.LINE_AA)

    # Legend swatches (right side) — compact for narrower panel
    sw = 12
    legend_items = [
        (S_GREEN,  ">=80%", vid_w - 200),
        (S_YELLOW, "60-79%", vid_w - 130),
        (S_RED,    "<60%",   vid_w -  60),
    ]
    for col, lbl, lx in legend_items:
        if lx > 0:
            y1, y2 = bar_h // 2 - sw // 2 + 4, bar_h // 2 + sw // 2 + 4
            cv2.rectangle(bar, (lx, y1), (lx + sw, y2), col, -1)
            cv2.putText(bar, lbl, (lx + sw + 3, y2 - 1),
                        FONT, 0.30, C_GRAY, 1, cv2.LINE_AA)

    # Main sync label (bottom row) — reference style
    main_txt = f"{sync_prefix} {overall:.1%}  |  frame {frame_idx:04d}"
    cv2.putText(bar, main_txt, (10, bar_h - 10),
                FONT, 0.58, C_WHITE, 2, cv2.LINE_AA)

    return bar


# ---------------------------------------------------------------------------
# Title card
# ---------------------------------------------------------------------------
def _make_title_card(w: int, h: int, fps: float, duration_sec: float = 3.0) -> list:
    n   = max(1, int(fps * duration_sec))
    bg  = np.zeros((h, w, 3), np.uint8)
    bg[:] = (18, 18, 18)
    gold = (30, 200, 220)
    cv2.rectangle(bg, (0, 0),      (w, 4),  gold, -1)
    cv2.rectangle(bg, (0, h - 4),  (w, h),  gold, -1)

    lines = [
        ("DANCE SIMILARITY ANALYSIS",           0.85, gold),
        ("Before vs After Code Optimization",   0.52, C_WHITE),
        ("Left: Loop Scoring (Slow)   |   Right: Vectorised + Face Guard (Fast)", 0.38, C_GRAY),
        ("Visual style: joint_scores_video.mp4", 0.32, (100, 100, 100)),
    ]
    start_y = h // 2 - (len(lines) * 42) // 2
    for li, (text, scale, color) in enumerate(lines):
        (tw, _), _ = cv2.getTextSize(text, FONT, scale, 2)
        tx = (w - tw) // 2
        ty = start_y + li * 46
        cv2.putText(bg, text, (tx + 2, ty + 2), FONT, scale, C_BLACK, 3, cv2.LINE_AA)
        cv2.putText(bg, text, (tx,     ty),     FONT, scale, color,   2, cv2.LINE_AA)

    return [bg.copy() for _ in range(n)]


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------
def _nvenc_available() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                           capture_output=True, text=True)
        return "h264_nvenc" in r.stdout
    except FileNotFoundError:
        return False


def _make_ffmpeg_cmd(out_path: str, w: int, h: int, fps: float) -> list:
    codec = (["h264_nvenc", "-preset", "p4", "-cq", "20"]
             if _nvenc_available() else
             ["libx264", "-preset", "fast", "-crf", "20"])
    return [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "bgr24",
        "-r", str(fps), "-i", "pipe:0",
        "-c:v", *codec,
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_trc", "bt709",
        "-color_primaries", "bt709", "-color_range", "tv",
        "-movflags", "+faststart",
        out_path,
    ]


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------
def render(video_path: Path, cache_path: Path, out_path: Path) -> None:
    # Load cached poses
    d       = np.load(str(cache_path))
    poses_a = list(d["pa"])   # list of (17,3) arrays
    poses_b = list(d["pb"])

    # Video dimensions
    cap      = cv2.VideoCapture(str(video_path))
    raw_w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    raw_h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps      = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = min(len(poses_a), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()

    # Scale so each panel fits in max_panel_w
    max_panel_w = 540
    sf = min(1.0, max_panel_w / raw_w)
    vid_w = int(raw_w * sf)
    vid_h = int(raw_h * sf)

    # Rescale keypoints once
    for kps in poses_a:
        kps[:, 0] *= sf
        kps[:, 1] *= sf
    for kps in poses_b:
        kps[:, 0] *= sf
        kps[:, 1] *= sf

    # Rendering parameters — same adaptive rules as reference
    font_scale = max(0.42, vid_w / 720 * 0.50)
    dot_r      = max(5, vid_w // 130)
    bar_h      = 70
    header_h   = 44

    panel_h = header_h + vid_h + bar_h
    out_w   = vid_w * 2
    out_h   = panel_h
    # Ensure even dimensions
    out_w  += out_w % 2
    out_h  += out_h % 2

    # Theme colors
    THEME_SLOW = _score_bgr(0.40)   # red  — slow/before
    THEME_FAST = _score_bgr(0.90)   # green — fast/after

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd  = _make_ffmpeg_cmd(str(out_path), out_w, out_h, fps)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Title card
    for f in _make_title_card(out_w, out_h, fps, 3.0):
        proc.stdin.write(f.tobytes())

    # Prepare pre-built header bars (constant per run)
    hdr_slow = _make_header(vid_w, header_h,
                            "BEFORE CODE OPTIMIZATION (SLOW)", THEME_SLOW)
    hdr_fast = _make_header(vid_w, header_h,
                            "AFTER CODE OPTIMIZATION (FAST)",  THEME_FAST)

    cap = cv2.VideoCapture(str(video_path))

    times_slow,  times_fast  = [], []
    scores_slow, scores_fast = [], []

    pbar = tqdm(total=n_frames, desc="Rendering compare_speed_video", unit="frame")

    for frame_idx in range(n_frames):
        ret, raw_frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(raw_frame, (vid_w, vid_h))
        pa    = poses_a[frame_idx]
        pb    = poses_b[frame_idx]

        # ── LEFT PANEL: Slow (Before) ─────────────────────────────────
        f_slow                  = frame.copy()
        jscores_slow, t_slow    = _score_slow(pa, pb)
        _annotate(f_slow, pa, pb, jscores_slow, font_scale, dot_r)

        # Dancer labels — reference style
        cv2.putText(f_slow, "A", (8, 28), FONT, 0.8, COLOR_A, 2, cv2.LINE_AA)
        cv2.putText(f_slow, "B", (8, 54), FONT, 0.8, COLOR_B, 2, cv2.LINE_AA)

        vis_s    = jscores_slow[~np.isnan(jscores_slow)]
        sync_s   = float(np.mean(vis_s)) if len(vis_s) else 0.0
        times_slow.append(t_slow)
        scores_slow.append(sync_s)

        bar_slow = _make_bar(
            vid_w, bar_h, sync_s, frame_idx,
            "Overall sync:", THEME_SLOW,
            algo_line  = "Loop x17 joints  |  No face guard  |  No early-exit",
            speed_line = f"Frame compute: {t_slow:.4f} ms",
        )
        left_panel = np.vstack([hdr_slow, f_slow, bar_slow])

        # ── RIGHT PANEL: Fast (After) ─────────────────────────────────
        f_fast = frame.copy()
        jscores_fast, t_fast, face_dir, early = _score_fast(pa, pb)
        _annotate(f_fast, pa, pb, jscores_fast, font_scale, dot_r)

        cv2.putText(f_fast, "A", (8, 28), FONT, 0.8, COLOR_A, 2, cv2.LINE_AA)
        cv2.putText(f_fast, "B", (8, 54), FONT, 0.8, COLOR_B, 2, cv2.LINE_AA)

        # Face-guard label (top-right)
        fd_col = THEME_FAST if face_dir == "front" else (0, 200, 230) if face_dir == "side" else THEME_SLOW
        cv2.putText(f_fast, f"Face: {face_dir.upper()}",
                    (vid_w - 140, 24), FONT, 0.42, fd_col, 1, cv2.LINE_AA)

        # Early-exit badge (top-right, below face label)
        if early:
            bx1, bx2 = vid_w - 140, vid_w - 4
            cv2.rectangle(f_fast, (bx1, 30), (bx2, 52), (200, 80, 0), -1)
            cv2.putText(f_fast, "EARLY EXIT", (bx1 + 4, 46),
                        FONT, 0.40, C_WHITE, 1, cv2.LINE_AA)

        vis_f  = jscores_fast[~np.isnan(jscores_fast)]
        sync_f = float(np.mean(vis_f)) if len(vis_f) else 0.0
        times_fast.append(t_fast)
        scores_fast.append(sync_f)

        speedup   = t_slow / max(t_fast, 1e-9)
        algo_line = "Vectorised numpy  |  Face guard ON"
        if early:
            algo_line += "  |  EARLY EXIT"
        speed_line = (f"Frame compute: {t_fast:.4f} ms  ({speedup:.1f}x faster)"
                      if speedup > 1.05 else
                      f"Frame compute: {t_fast:.4f} ms")

        bar_fast = _make_bar(
            vid_w, bar_h, sync_f, frame_idx,
            "Overall sync:", THEME_FAST,
            algo_line  = algo_line,
            speed_line = speed_line,
        )
        right_panel = np.vstack([hdr_fast, f_fast, bar_fast])

        # ── Composite ─────────────────────────────────────────────────
        canvas = np.hstack([left_panel, right_panel])

        # Centre divider line
        cv2.line(canvas, (vid_w, 0), (vid_w, out_h), C_WHITE, 2)

        # Fit to declared output dimensions
        if canvas.shape[1] != out_w or canvas.shape[0] != out_h:
            canvas = canvas[:out_h, :out_w]

        try:
            proc.stdin.write(canvas.tobytes())
        except BrokenPipeError:
            break

        pbar.update(1)

    pbar.close()
    cap.release()
    proc.stdin.close()
    proc.wait()

    # ── Summary ───────────────────────────────────────────────────────
    mean_sync_s  = float(np.mean(scores_slow)) * 100
    mean_sync_f  = float(np.mean(scores_fast)) * 100
    mean_t_slow  = float(np.mean(times_slow))
    mean_t_fast  = float(np.mean(times_fast))
    speedup_mean = mean_t_slow / max(mean_t_fast, 1e-9)
    n_early      = sum(1 for s in scores_fast if s == 0.0)  # early-exit proxy

    print(f"\n{'='*60}")
    print(f"  Output                  : {out_path}")
    print(f"  Frames                  : {n_frames}  @  {fps:.1f} fps")
    print(f"  Avg sync  Before (Slow) : {mean_sync_s:.1f}%")
    print(f"  Avg sync  After  (Fast) : {mean_sync_f:.1f}%")
    print(f"  Avg time  Before (Slow) : {mean_t_slow:.5f} ms/frame")
    print(f"  Avg time  After  (Fast) : {mean_t_fast:.5f} ms/frame")
    print(f"  Mean speedup            : {speedup_mean:.2f}x faster")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not _VIDEO.exists():
        sys.exit(f"Video not found: {_VIDEO}\n"
                 "Run analyze_duet.py in the dance_similarity project first.")
    if not _CACHE.exists():
        sys.exit(f"Pose cache not found: {_CACHE}\n"
                 "Run analyze_duet.py first to extract and cache poses.")

    print(f"\nSource video : {_VIDEO}")
    print(f"Pose cache   : {_CACHE}")
    print(f"Output       : {_OUT_VIDEO}\n")

    render(_VIDEO, _CACHE, _OUT_VIDEO)
