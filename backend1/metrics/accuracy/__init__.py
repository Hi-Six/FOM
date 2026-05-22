"""
Per-joint matching rate video renderer.

For every frame, computes how well each of the 17 COCO keypoints aligns
between the two dancers (in normalised pose space, so position/scale are
removed). Renders the per-joint score as a coloured percentage label directly
on each keypoint, plus a connecting line between each matched joint pair.

Color coding
------------
  Green  >= 80 % -- well matched
  Yellow 60-79 % -- moderate drift
  Red    < 60 %  -- significant mismatch

Requires
--------
  data/duet.mp4           -- source video (from analyze_duet.py)
  data/.cache_duet.npz    -- cached poses   (from analyze_duet.py)

Usage
-----
  python -m feature_accuracy.backend1.metrics.accuracy
  python -m feature_accuracy.backend1.metrics.accuracy --video data/duet.mp4 --cache data/.cache_duet.npz
"""

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

# ── Paths ───────────────────────────────────────────────────────────────────
DATA           = Path("data")
OUTPUT         = Path("output")
_DEFAULT_VIDEO = DATA   / "duet.mp4"
_DEFAULT_CACHE = DATA   / ".cache_duet.npz"
_OUT_VIDEO     = OUTPUT / "joint_scores_video.mp4"

# ── COCO-17 joint short names for on-screen labels ─────────────────────────
JOINT_NAMES = [
    "nose", "L.eye", "R.eye", "L.ear", "R.ear",
    "L.shl", "R.shl", "L.elb", "R.elb",
    "L.wri", "R.wri", "L.hip", "R.hip",
    "L.kne", "R.kne", "L.ank", "R.ank",
]

# ── Per-dancer skeleton colours (BGR) ──────────────────────────────────────
COLOR_A = (230, 190,  30)   # warm yellow -- Dancer A
COLOR_B = ( 30, 120, 255)   # vivid orange -- Dancer B

# ── Normalised-space tolerance for per-joint Gaussian score ────────────────
# 0.30 = ~30 % of torso height; exp(-d^2/2t^2) gives 37 % at d = t
JOINT_TOLERANCE = 0.30

# ── COCO-17 / 40-kp skeleton edges ─────────────────────────────────────────
# Inlined from dance_similarity/src/keypoint_expander.py.
# Edges referencing indices >= 17 are silently skipped when drawing 17-kp poses.
SKELETON_40 = [
    # original COCO-17
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    # neck / spine chain
    (17, 0),  (17, 5),  (17, 6),
    (17, 18), (18, 19), (19, 20), (20, 21),
    (21, 11), (21, 12),
    # upper chest crossbar
    (18, 5),  (18, 6),
    # arm segments
    (24, 5), (24, 7),
    (25, 6), (25, 8),
    (22, 7), (22, 9),
    (23, 8), (23, 10),
    (38, 9), (39, 10),
    # leg segments
    (26, 11), (26, 13),
    (27, 12), (27, 14),
    (28, 13), (28, 15),
    (29, 14), (29, 16),
    (30, 15), (31, 16),
    (32, 15), (33, 16),
    # face
    (34, 0), (35, 0),
    (36, 1), (36, 3),
    (37, 2), (37, 4),
]


# ── Pose normalisation ──────────────────────────────────────────────────────
# Inlined from dance_similarity/src/aihub_loader.py :: normalize_pose.

def normalize_pose(kps: np.ndarray) -> np.ndarray:
    """
    Return a normalised copy of kps (17, 3).

    Centres on the hip midpoint and scales by torso height (hip midpoint to
    shoulder midpoint). Invisible keypoints (v == 0) are kept as zeros so
    they do not contaminate the similarity calculation.
    """
    out     = kps.copy()
    visible = kps[:, 2] > 0

    if visible[11] and visible[12]:
        hip_mid = (kps[11, :2] + kps[12, :2]) / 2.0
    elif visible[11]:
        hip_mid = kps[11, :2]
    elif visible[12]:
        hip_mid = kps[12, :2]
    else:
        return out

    if visible[5] and visible[6]:
        shoulder_mid = (kps[5, :2] + kps[6, :2]) / 2.0
    elif visible[5]:
        shoulder_mid = kps[5, :2]
    elif visible[6]:
        shoulder_mid = kps[6, :2]
    else:
        return out

    torso_h = np.linalg.norm(shoulder_mid - hip_mid)
    if torso_h < 1e-6:
        return out

    out[:, :2] = (kps[:, :2] - hip_mid) / torso_h
    out[~visible, :2] = 0.0
    return out


# ── Score -> colour (BGR) ───────────────────────────────────────────────────

def _score_bgr(score: float) -> tuple:
    if score >= 0.80:
        return (50, 210, 60)    # green
    elif score >= 0.60:
        return (0, 200, 230)    # yellow
    else:
        return (50, 60, 230)    # red


# ── Per-joint scoring ───────────────────────────────────────────────────────

def per_joint_scores(pa: np.ndarray, pb: np.ndarray) -> np.ndarray:
    """
    Compute per-joint Gaussian similarity between two (17, 3) raw poses.
    Both poses are normalised (centred + torso-scale) before comparison,
    so position and body size are factored out.

    Returns (17,) array; np.nan where either joint is invisible.
    """
    na     = normalize_pose(pa)
    nb     = normalize_pose(pb)
    scores = np.full(17, np.nan, dtype=np.float32)
    denom  = 2.0 * JOINT_TOLERANCE ** 2
    for i in range(17):
        if na[i, 2] > 0.1 and nb[i, 2] > 0.1:
            d2 = float(((na[i, :2] - nb[i, :2]) ** 2).sum())
            scores[i] = np.exp(-d2 / denom)
    return scores


# ── Skeleton bone drawing ───────────────────────────────────────────────────

def _draw_bones(img: np.ndarray, kps: np.ndarray, color: tuple) -> None:
    """Draw skeleton bone connections for a single person (17-kp array)."""
    h, w = img.shape[:2]
    n    = len(kps)
    vis  = {i: (int(kps[i, 0]), int(kps[i, 1]))
            for i in range(n)
            if kps[i, 2] > 0.1 and 0 <= kps[i, 0] < w and 0 <= kps[i, 1] < h}
    for a, b in SKELETON_40:
        if a < n and b < n and a in vis and b in vis:
            cv2.line(img, vis[a], vis[b], color, 2, cv2.LINE_AA)


# ── Single-frame annotation ─────────────────────────────────────────────────

def _annotate(img: np.ndarray, pa: np.ndarray, pb: np.ndarray,
              joint_scores: np.ndarray, font_scale: float, dot_r: int) -> None:
    """
    Draw per-joint matching rates onto img (in-place):

      1. Bone connections for both dancers underneath everything
      2. Score-coloured dots at each visible joint pair
      3. Score "87%" label at each joint (score colour, dark outline)
      4. Tiny joint-name label below each dot (white)
    """
    h, w = img.shape[:2]
    FONT       = cv2.FONT_HERSHEY_SIMPLEX
    name_scale = max(0.28, font_scale * 0.55)

    _draw_bones(img, pa, COLOR_A)
    _draw_bones(img, pb, COLOR_B)

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

            for cx, cy in [(ax, ay), (bx, by)]:
                cv2.circle(img, (cx, cy), dot_r + 1, (0, 0, 0), -1, cv2.LINE_AA)
                cv2.circle(img, (cx, cy), dot_r,     color,      -1, cv2.LINE_AA)

            for cx, cy in [(ax, ay), (bx, by)]:
                tx = min(cx + dot_r + 3, w - 38)
                ty = max(cy - dot_r - 3, 14)
                cv2.putText(img, pct, (tx, ty), FONT, font_scale,
                            (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(img, pct, (tx, ty), FONT, font_scale,
                            color, 1, cv2.LINE_AA)

            name = JOINT_NAMES[i]
            for cx, cy in [(ax, ay), (bx, by)]:
                nx = max(cx - 14, 2)
                ny = min(cy + dot_r + 12, h - 2)
                cv2.putText(img, name, (nx, ny), FONT, name_scale,
                            (0, 0, 0),       2, cv2.LINE_AA)
                cv2.putText(img, name, (nx, ny), FONT, name_scale,
                            (240, 240, 240), 1, cv2.LINE_AA)

        else:
            if vis_a:
                ax, ay = int(pa[i, 0]), int(pa[i, 1])
                cv2.circle(img, (ax, ay), dot_r, COLOR_A, -1, cv2.LINE_AA)
            if vis_b:
                bx, by = int(pb[i, 0]), int(pb[i, 1])
                cv2.circle(img, (bx, by), dot_r, COLOR_B, -1, cv2.LINE_AA)


# ── NVENC check ─────────────────────────────────────────────────────────────

def _nvenc_available() -> bool:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                       capture_output=True, text=True)
    return "h264_nvenc" in r.stdout


# ── Main renderer ────────────────────────────────────────────────────────────

def render(video_path: Path, cache_path: Path, out_path: Path) -> None:
    d       = np.load(cache_path)
    poses_a = list(d["pa"])
    poses_b = list(d["pb"])

    cap      = cv2.VideoCapture(str(video_path))
    vid_w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps      = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = min(len(poses_a), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))

    bar_h   = 70
    total_h = vid_h + bar_h

    font_scale = max(0.42, vid_w / 720 * 0.50)
    dot_r      = max(5, vid_w // 130)

    codec_args = (["h264_nvenc", "-preset", "p4", "-cq", "20"]
                  if _nvenc_available() else
                  ["libx264", "-preset", "fast", "-crf", "20"])
    print(f"Encoder: {'h264_nvenc (GPU)' if 'nvenc' in codec_args[0] else 'libx264 (CPU)'}")
    print(f"Output : {vid_w} x {total_h}  @  {fps:.2f} fps")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{vid_w}x{total_h}", "-pix_fmt", "bgr24",
        "-r", str(fps), "-i", "pipe:0",
        "-c:v", *codec_args,
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_trc", "bt709",
        "-color_primaries", "bt709", "-color_range", "tv",
        "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    GREEN  = _score_bgr(0.90)
    YELLOW = _score_bgr(0.70)
    RED    = _score_bgr(0.40)

    try:
        pbar      = tqdm(total=n_frames, desc="Rendering joint-score video", unit="frame")
        frame_idx = 0

        while frame_idx < n_frames:
            ret, frame = cap.read()
            if not ret:
                break

            pa = poses_a[frame_idx]
            pb = poses_b[frame_idx]

            jscores = per_joint_scores(pa, pb)

            _annotate(frame, pa, pb, jscores, font_scale, dot_r)

            cv2.putText(frame, "A", (8, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_A, 2, cv2.LINE_AA)
            cv2.putText(frame, "B", (8, 54),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_B, 2, cv2.LINE_AA)

            visible = jscores[~np.isnan(jscores)]
            overall = float(np.mean(visible)) if len(visible) else 0.0

            bar  = np.zeros((bar_h, vid_w, 3), np.uint8)
            fill = int(overall * vid_w)
            bar[:, :fill] = _score_bgr(overall)

            sw = 16
            for col, lbl, lx in [
                (GREEN,  ">=80% matched",  vid_w - 310),
                (YELLOW, "60-79% drift",   vid_w - 200),
                (RED,    "<60% mismatch",  vid_w - 100),
            ]:
                if lx > 0:
                    cv2.rectangle(bar, (lx, bar_h // 2 - sw // 2),
                                  (lx + sw, bar_h // 2 + sw // 2), col, -1)

            cv2.putText(bar,
                        f"Overall sync: {overall:.1%}  |  frame {frame_idx:04d}",
                        (10, bar_h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

            out_frame = np.vstack([frame, bar])
            proc.stdin.write(out_frame.tobytes())

            frame_idx += 1
            pbar.update(1)

    finally:
        pbar.close()
        proc.stdin.close()
        proc.wait()
        cap.release()

    print(f"\nJoint-score video -> {out_path}")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Render a video with per-joint matching rates displayed on screen")
    ap.add_argument("--video", default=str(_DEFAULT_VIDEO),
                    help="Source video (default: data/duet.mp4)")
    ap.add_argument("--cache", default=str(_DEFAULT_CACHE),
                    help="Cached pose NPZ (default: data/.cache_duet.npz)")
    ap.add_argument("--out",   default=str(_OUT_VIDEO),
                    help="Output video path")
    args = ap.parse_args()

    video_path = Path(args.video)
    cache_path = Path(args.cache)
    out_path   = Path(args.out)

    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}\n"
                 "Run analyze_duet.py first to download the video.")
    if not cache_path.exists():
        sys.exit(f"Pose cache not found: {cache_path}\n"
                 "Run analyze_duet.py first to extract poses.")

    print(f"\nSource video : {video_path}")
    print(f"Pose cache   : {cache_path}")
    print(f"Output       : {out_path}\n")

    render(video_path, cache_path, out_path)


if __name__ == "__main__":
    main()