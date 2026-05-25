# -*- coding: utf-8 -*-
"""
compare_video.py
================
Generates a Before/After dual-person detection comparison video.

  BEFORE  -- single-person detection (old code): only Person A is tracked;
             Person B is invisible to the system.
  AFTER   -- dual-person detection (new code): both Person A and Person B
             are tracked simultaneously with individual accuracy/confidence
             scores and a cross-person matching score.
  COMPARE -- split-screen side-by-side (left=Before, right=After).

Usage
-----
    python -m metrics.accuracy.compare_video --video data/shorts.mp4

    Output:  output/compare_before_after.mp4

Requirements
------------
    pip install mediapipe opencv-python-headless numpy tqdm
"""

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

try:
    import mediapipe as mp
    _HAS_MP = True
except ImportError:
    _HAS_MP = False

# ---------------------------------------------------------------------------
# COCO-17 <- MediaPipe-33 index mapping
# ---------------------------------------------------------------------------
_MP33_TO_COCO17 = [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]

JOINT_NAMES = [
    "nose", "L.eye", "R.eye", "L.ear", "R.ear",
    "L.shl", "R.shl", "L.elb", "R.elb",
    "L.wri", "R.wri", "L.hip", "R.hip",
    "L.kne", "R.kne", "L.ank", "R.ank",
]

COCO17_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

JOINT_WEIGHTS = np.array([
    0.5, 0.3, 0.3, 0.2, 0.2,
    1.2, 1.2, 1.0, 1.0, 1.0, 1.0,
    1.2, 1.2, 1.0, 1.0, 1.0, 1.0,
], dtype=np.float32)

JOINT_TOLERANCE   = 0.30
SIM_THRESHOLD     = 0.65
FACE_VIS_GATE     = 0.30
FACE_INDICES      = frozenset({0, 1, 2, 3, 4})
STRUCT_JOINTS     = [5, 6, 11, 12]

# visual
C_RED      = (60,  60,  220)    # BGR  before theme
C_GREEN    = (50,  210,  60)    # BGR  after  theme
C_WHITE    = (255, 255, 255)
C_BLACK    = (0,   0,   0)
C_GOLD     = (30,  200, 220)
C_GRAY     = (120, 120, 120)
C_YELLOW   = (0,   200, 230)
C_PERSON_A = (230, 200,  50)    # BGR  cyan-gold — Person A skeleton
C_PERSON_B = (30,  130, 255)    # BGR  orange    — Person B skeleton
FONT       = cv2.FONT_HERSHEY_SIMPLEX

HUD_H = 160   # bottom HUD height (extra rows for dual-person scores)


# ---------------------------------------------------------------------------
# MediaPipe extraction — dual-person
# ---------------------------------------------------------------------------

def _ensure_mediapipe():
    if not _HAS_MP:
        sys.exit("mediapipe not installed.  Run:  pip install mediapipe")


def extract_coco17_poses(video_path: str) -> tuple:
    """
    Extract COCO-17 poses for up to 2 persons per frame.

    Returns
    -------
    poses_a : list of np.ndarray  shape (17, 3)  -- Person A [x_px, y_px, vis]
    poses_b : list of np.ndarray  shape (17, 3)  -- Person B (zeros if absent)
    frames  : list of np.ndarray  raw BGR frames
    fps     : float
    """
    _ensure_mediapipe()

    BaseOptions        = mp.tasks.BaseOptions
    PoseLandmarker     = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOpts = mp.tasks.vision.PoseLandmarkerOptions
    RunningMode        = mp.tasks.vision.RunningMode

    model_candidates = [
        Path("C:/fom_mediapipe_cache/pose_landmarker_full.task"),
        Path("metrics/rom/models/pose_landmarker_full.task"),
        Path("models/pose_landmarker_full.task"),
    ]
    model_path = None
    for c in model_candidates:
        if c.exists():
            model_path = str(c)
            break
    if model_path is None:
        sys.exit(
            "MediaPipe model not found.  Expected one of:\n"
            + "\n".join(f"  {c}" for c in model_candidates)
        )

    opts = PoseLandmarkerOpts(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.VIDEO,
        num_poses=2,                          # detect both persons simultaneously
        min_pose_detection_confidence=0.45,
        min_pose_presence_confidence=0.45,
        min_tracking_confidence=0.45,
    )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"Cannot open video: {video_path}")

    fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    poses_a_out = []
    poses_b_out = []
    frames_out  = []
    frame_idx   = 0

    print(f"Extracting poses from {video_path}  [{w}x{h} @ {fps:.1f}fps, ~{total} frames]")
    print("Dual-person detection enabled (num_poses=2)")

    with PoseLandmarker.create_from_options(opts) as lm:
        pbar = tqdm(total=total, desc="MediaPipe extraction", unit="frame")
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms  = int(frame_idx * 1000 / fps)
            result = lm.detect_for_video(mp_img, ts_ms)

            kps_a = np.zeros((17, 3), dtype=np.float32)
            kps_b = np.zeros((17, 3), dtype=np.float32)

            if result.pose_landmarks:
                for person_idx, person_kps in enumerate([kps_a, kps_b]):
                    if person_idx < len(result.pose_landmarks):
                        lms = result.pose_landmarks[person_idx]
                        for coco_i, mp_i in enumerate(_MP33_TO_COCO17):
                            lm_pt = lms[mp_i]
                            person_kps[coco_i] = [lm_pt.x * w, lm_pt.y * h, lm_pt.visibility]

            poses_a_out.append(kps_a)
            poses_b_out.append(kps_b)
            frames_out.append(frame.copy())
            frame_idx += 1
            pbar.update(1)
        pbar.close()

    cap.release()
    return poses_a_out, poses_b_out, frames_out, fps


# ---------------------------------------------------------------------------
# Synthetic Person B (for videos with only one real person)
# ---------------------------------------------------------------------------

def make_user_poses(ref_poses: list, rng_seed: int = 7) -> list:
    """Derive synthetic Person B from Person A (noise + face-turn injection)."""
    rng    = np.random.default_rng(rng_seed)
    result = []
    for i, kps in enumerate(ref_poses):
        usr = kps.copy()
        usr[:, :2] += rng.normal(0, 4.0, (17, 2)).astype(np.float32)
        if i % 12 == 0 and i > 0:
            usr[0, 2] = 0.15
            usr[1, 2] = 0.10
            usr[2, 2] = 0.10
            usr[3, 2] = 0.08
            usr[4, 2] = min(kps[4, 2], 0.85)
        result.append(usr)
    return result


# ---------------------------------------------------------------------------
# Pose normalisation
# ---------------------------------------------------------------------------

def _normalize(kps: np.ndarray):
    out = kps.copy().astype(np.float32)
    vis = kps[:, 2] > 0
    if vis[11] and vis[12]:
        hip = (kps[11, :2] + kps[12, :2]) / 2.0
    elif vis[11]:
        hip = kps[11, :2]
    elif vis[12]:
        hip = kps[12, :2]
    else:
        return None
    if vis[5] and vis[6]:
        shl = (kps[5, :2] + kps[6, :2]) / 2.0
    elif vis[5]:
        shl = kps[5, :2]
    elif vis[6]:
        shl = kps[6, :2]
    else:
        return None
    torso = float(np.linalg.norm(shl - hip))
    if torso < 1e-4:
        return None
    out[:, :2] = (kps[:, :2] - hip) / torso
    out[~vis, :2] = 0.0
    return out


# ---------------------------------------------------------------------------
# Scoring (vectorised + face-direction guard + early-exit)
# ---------------------------------------------------------------------------

def _face_dir(kps: np.ndarray) -> str:
    l_ok = float(kps[3, 2]) > FACE_VIS_GATE
    r_ok = float(kps[4, 2]) > FACE_VIS_GATE
    if l_ok and r_ok:
        return "front"
    if not l_ok and not r_ok:
        return "back"
    return "side"


def score_after(pa: np.ndarray, pb: np.ndarray) -> tuple:
    """Returns (scores_array, face_direction_str, early_exit_bool)."""
    na = _normalize(pa)
    nb = _normalize(pb)
    scores = np.full(17, np.nan, dtype=np.float32)
    if na is None or nb is None:
        return scores, "unknown", False

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

    denom      = 2.0 * JOINT_TOLERANCE ** 2
    early_exit = False
    if struct.any():
        d2_s   = ((na[struct, :2] - nb[struct, :2]) ** 2).sum(axis=1)
        coarse = float(np.mean(np.exp(-d2_s / denom)))
        if coarse < SIM_THRESHOLD / 2:
            scores[struct] = np.exp(-d2_s / denom)
            return scores, face_dir_label, True

    if valid.any():
        d2 = ((na[valid, :2] - nb[valid, :2]) ** 2).sum(axis=1)
        scores[valid] = np.exp(-d2 / denom)

    return scores, face_dir_label, early_exit


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

def _frame_score(scores: np.ndarray) -> float:
    vis = ~np.isnan(scores)
    if not vis.any():
        return 0.0
    return float(np.average(scores[vis], weights=JOINT_WEIGHTS[vis]))


def _person_confidence(kps: np.ndarray) -> float:
    """Weighted mean visibility of joints detected above threshold."""
    vis = kps[:, 2] > 0.1
    if not vis.any():
        return 0.0
    return float(np.average(kps[vis, 2], weights=JOINT_WEIGHTS[vis]))


def _score_color(s: float) -> tuple:
    if s >= SIM_THRESHOLD:
        return C_GREEN
    if s >= 0.60:
        return C_YELLOW
    return C_RED


# ---------------------------------------------------------------------------
# Drawing utilities
# ---------------------------------------------------------------------------

def _put(img, text, x, y, scale=0.55, color=C_WHITE, thick=1, shadow=True):
    if shadow:
        cv2.putText(img, text, (x + 1, y + 1), FONT, scale, C_BLACK, thick + 1, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), FONT, scale, color, thick, cv2.LINE_AA)


def _draw_skeleton(img, kps, color, alpha=0.85):
    h, w = img.shape[:2]
    overlay = img.copy()
    pts = {}
    for i in range(17):
        if kps[i, 2] > 0.1:
            px, py = int(kps[i, 0]), int(kps[i, 1])
            if 0 <= px < w and 0 <= py < h:
                pts[i] = (px, py)
    for a, b in COCO17_EDGES:
        if a in pts and b in pts:
            cv2.line(overlay, pts[a], pts[b], color, 2, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def _draw_joints(img, kps_a, kps_b, scores, dot_r=7):
    h, w = img.shape[:2]
    for i in range(17):
        vis_a = kps_a[i, 2] > 0.1
        vis_b = kps_b[i, 2] > 0.1
        s     = scores[i]
        if vis_a and vis_b and not np.isnan(s):
            ax, ay = int(kps_a[i, 0]), int(kps_a[i, 1])
            bx, by = int(kps_b[i, 0]), int(kps_b[i, 1])
            col    = _score_color(float(s))
            for px, py in [(ax, ay), (bx, by)]:
                if 0 <= px < w and 0 <= py < h:
                    cv2.circle(img, (px, py), dot_r + 1, C_BLACK, -1, cv2.LINE_AA)
                    cv2.circle(img, (px, py), dot_r,     col,     -1, cv2.LINE_AA)
                    _put(img, f"{int(s*100)}%", px + dot_r + 2, py - dot_r,
                         scale=0.38, color=col, thick=1, shadow=True)


def _draw_header(img, title: str, frame_idx: int, theme_color):
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, 0), (w, 44), (15, 15, 15), -1)
    cv2.line(img, (0, 44), (w, 44), theme_color, 2)
    _put(img, title, 14, 30, scale=0.65, color=theme_color, thick=2)
    _put(img, f"Frame {frame_idx:04d}", w - 140, 30, scale=0.50, color=C_GRAY, thick=1)


def _draw_score_bar(img, x, y, w, score, color, label, bar_h=18):
    """Draw a labelled horizontal score bar; returns the y position after it."""
    bar_w = max(int(score * (w - 4)), 3)
    cv2.rectangle(img, (x, y), (x + w, y + bar_h), (55, 55, 55), -1)
    cv2.rectangle(img, (x, y), (x + bar_w, y + bar_h), color, -1)
    _put(img, f"{label}: {score*100:.1f}%", x + 4, y + bar_h - 3,
         scale=0.42, color=C_WHITE, thick=1, shadow=True)
    return y + bar_h + 4


# ---------------------------------------------------------------------------
# HUD drawers
# ---------------------------------------------------------------------------

def _draw_hud_before(img, conf_a: float, n_joints: int):
    """Single-person HUD — red theme, 'Person B: NOT DETECTED' warning."""
    h, w = img.shape[:2]
    hud_y0 = h - HUD_H
    cv2.rectangle(img, (0, hud_y0), (w, h), (20, 20, 20), -1)
    cv2.line(img, (0, hud_y0), (w, hud_y0), C_RED, 2)

    margin = 10
    bar_w  = w - margin * 2
    y = hud_y0 + 10
    y = _draw_score_bar(img, margin, y, bar_w, conf_a, C_RED, "Person A Confidence")

    # "Person B: NOT DETECTED" warning box
    cv2.rectangle(img, (margin, y), (margin + bar_w, y + 20), (40, 20, 20), -1)
    cv2.rectangle(img, (margin, y), (margin + bar_w, y + 20), C_RED, 1)
    _put(img, "Person B: NOT DETECTED  (single-person mode — old code)",
         margin + 6, y + 15, scale=0.42, color=C_RED, thick=1, shadow=False)
    y += 24

    _put(img, f"Joints tracked: {n_joints}/17", margin, y + 2,
         scale=0.40, color=C_GRAY)
    _put(img, "Mode: Single Person Detection (Before)", margin + 160, y + 2,
         scale=0.40, color=C_RED)
    y += 20
    _put(img, "Cross-Person Match Score: N/A  (requires 2 persons)",
         margin, y + 2, scale=0.38, color=C_GRAY)
    y += 18
    _put(img, f"Threshold: {SIM_THRESHOLD:.0%}  |  Tolerance: {JOINT_TOLERANCE}",
         margin, y + 2, scale=0.35, color=C_GRAY)


def _draw_hud_after(img, conf_a: float, conf_b: float, match_score: float,
                    face_dir: str, early_exit: bool, n_joints: int):
    """Dual-person HUD — green theme with Person A, Person B, and match bars."""
    h, w = img.shape[:2]
    hud_y0 = h - HUD_H
    cv2.rectangle(img, (0, hud_y0), (w, h), (20, 20, 20), -1)
    cv2.line(img, (0, hud_y0), (w, hud_y0), C_GREEN, 2)

    margin = 10
    bar_w  = w - margin * 2
    y = hud_y0 + 10
    y = _draw_score_bar(img, margin, y, bar_w, conf_a,     C_PERSON_A, "Person A Accuracy")
    y = _draw_score_bar(img, margin, y, bar_w, conf_b,     C_PERSON_B, "Person B Accuracy")
    y = _draw_score_bar(img, margin, y, bar_w, match_score, _score_color(match_score), "A vs B Match Score")

    _put(img, f"Joints: {n_joints}/17", margin, y + 2, scale=0.40, color=C_GRAY)
    _put(img, "Mode: Dual Person Detection (After)", margin + 120, y + 2,
         scale=0.40, color=C_GREEN)
    if face_dir and face_dir != "unknown":
        fd_col = C_GREEN if face_dir == "front" else C_YELLOW if face_dir == "side" else C_RED
        _put(img, f"Face: {face_dir.upper()}", w - 160, y + 2,
             scale=0.40, color=fd_col)
    y += 20

    _put(img, f"Threshold: {SIM_THRESHOLD:.0%}  |  Tolerance: {JOINT_TOLERANCE}",
         margin, y + 2, scale=0.35, color=C_GRAY)
    if early_exit:
        _put(img, "EARLY EXIT", w - 110, y + 2, scale=0.35, color=(0, 200, 255))


# ---------------------------------------------------------------------------
# Title card generator
# ---------------------------------------------------------------------------

def make_title_card(w: int, h: int, fps: float,
                    lines: list, accent_color, duration_sec: float = 2.5) -> list:
    n  = max(1, int(fps * duration_sec))
    bg = np.zeros((h, w, 3), np.uint8)
    bg[:] = (18, 18, 18)
    cv2.rectangle(bg, (0, 0), (w, 4), accent_color, -1)
    cv2.rectangle(bg, (0, h - 4), (w, h), accent_color, -1)

    start_y = h // 2 - (len(lines) * 38) // 2
    for li, (text, scale, color) in enumerate(lines):
        (tw, _), _ = cv2.getTextSize(text, FONT, scale, 2)
        tx = (w - tw) // 2
        ty = start_y + li * 42
        cv2.putText(bg, text, (tx + 2, ty + 2), FONT, scale, C_BLACK, 3, cv2.LINE_AA)
        cv2.putText(bg, text, (tx, ty), FONT, scale, color, 2, cv2.LINE_AA)

    return [bg.copy() for _ in range(n)]


# ---------------------------------------------------------------------------
# Per-frame renderers
# ---------------------------------------------------------------------------

def render_frame_before(bgr, kps_a, frame_idx):
    """BEFORE: single-person detection — only Person A skeleton shown."""
    img = bgr.copy()
    _draw_skeleton(img, kps_a, C_RED)

    # Label Person A near left shoulder
    if kps_a[5, 2] > 0.1:
        lx = max(int(kps_a[5, 0]) - 30, 0)
        ly = max(int(kps_a[5, 1]) - 10, 50)
        _put(img, "A", lx, ly, scale=0.65, color=C_RED, thick=2)

    conf_a   = _person_confidence(kps_a)
    n_joints = int((kps_a[:, 2] > 0.1).sum())
    _draw_header(img, "BEFORE CODE MODIFICATION", frame_idx, C_RED)
    _draw_hud_before(img, conf_a, n_joints)
    return img, conf_a


def render_frame_after(bgr, kps_a, kps_b, frame_idx):
    """AFTER: dual-person detection — Person A (cyan) + Person B (orange)."""
    img = bgr.copy()
    _draw_skeleton(img, kps_a, C_PERSON_A)
    _draw_skeleton(img, kps_b, C_PERSON_B)

    scores, face_dir, early = score_after(kps_a, kps_b)
    _draw_joints(img, kps_a, kps_b, scores)

    match_score = _frame_score(scores)
    conf_a      = _person_confidence(kps_a)
    conf_b      = _person_confidence(kps_b)
    n_joints    = int((~np.isnan(scores)).sum())

    # Label each person near their left shoulder
    for kps, label, color in [(kps_a, "A", C_PERSON_A), (kps_b, "B", C_PERSON_B)]:
        if kps[5, 2] > 0.1:
            lx = max(int(kps[5, 0]) - 30, 0)
            ly = max(int(kps[5, 1]) - 10, 50)
            _put(img, label, lx, ly, scale=0.65, color=color, thick=2)

    _draw_header(img, "AFTER CODE MODIFICATION", frame_idx, C_GREEN)
    _draw_hud_after(img, conf_a, conf_b, match_score, face_dir, early, n_joints)
    return img, conf_a, conf_b, match_score


# ---------------------------------------------------------------------------
# Helpers for split-screen HUD
# ---------------------------------------------------------------------------

def _joint_gauge(canvas, x, y, w, evaluated: int, label_color):
    seg_w   = max(4, (w - 2) // 17)
    total_w = seg_w * 17
    x0      = x + (w - total_w) // 2
    for j in range(17):
        x1     = x0 + j * seg_w
        col    = label_color if j < evaluated else (45, 45, 45)
        cv2.rectangle(canvas, (x1 + 1, y), (x1 + seg_w - 1, y + 9), col, -1)
    _put(canvas, f"{evaluated}/17 joints", x0, y + 22,
         scale=0.38, color=label_color, thick=1, shadow=True)


def _badge(canvas, x, y, text, bg_col, txt_col=None, pad_x=8, pad_y=4):
    txt_col     = txt_col or C_WHITE
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.40, 1)
    x2 = x + tw + pad_x * 2
    y2 = y + th + pad_y * 2
    cv2.rectangle(canvas, (x, y), (x2, y2), bg_col, -1)
    cv2.rectangle(canvas, (x, y), (x2, y2), (180, 180, 180), 1)
    cv2.putText(canvas, text, (x + pad_x, y2 - pad_y - 1),
                FONT, 0.40, txt_col, 1, cv2.LINE_AA)
    return x2, y2


# ---------------------------------------------------------------------------
# Split-screen frame builder
# ---------------------------------------------------------------------------

def render_split_frame(bgr, kps_a, kps_b, frame_idx, out_w, out_h,
                       cum_before: float = 0.0, cum_match: float = 0.0):
    """
    Left  = BEFORE: single-person detection (red theme)
    Right = AFTER:  dual-person detection   (cyan + orange theme)
    Returns (canvas, conf_a_before, match_score_after)
    """
    half_w  = out_w // 2
    panel_h = out_h - HUD_H
    orig_h, orig_w = bgr.shape[:2]

    def _scale_kps(kps, sw, sh):
        k = kps.copy()
        k[:, 0] *= sw / orig_w
        k[:, 1] *= sh / orig_h
        return k

    # ── LEFT PANEL: before (single-person) ───────────────────────────────
    left_bgr = cv2.resize(bgr, (half_w, panel_h))
    ref_l    = _scale_kps(kps_a, half_w, panel_h)
    _draw_skeleton(left_bgr, ref_l, C_RED)
    conf_a_b = _person_confidence(kps_a)
    n_jts_b  = int((kps_a[:, 2] > 0.1).sum())

    # ── RIGHT PANEL: after (dual-person) ─────────────────────────────────
    right_bgr = cv2.resize(bgr, (half_w, panel_h))
    ref_r     = _scale_kps(kps_a, half_w, panel_h)
    usr_r     = _scale_kps(kps_b, half_w, panel_h)
    _draw_skeleton(right_bgr, ref_r, C_PERSON_A)
    _draw_skeleton(right_bgr, usr_r, C_PERSON_B)
    sc_a, face_dir, early = score_after(kps_a, kps_b)
    _draw_joints(right_bgr, ref_r, usr_r, sc_a, dot_r=5)
    match_score = _frame_score(sc_a)
    conf_a_a    = _person_confidence(kps_a)
    conf_b_a    = _person_confidence(kps_b)
    n_jts_a     = int((~np.isnan(sc_a)).sum())
    b_detected  = bool(kps_b[:, 2].max() > 0.1)

    HEADER_H = 44

    # Left header
    cv2.rectangle(left_bgr,  (0, 0), (half_w, HEADER_H), (35, 18, 18), -1)
    cv2.line(left_bgr, (0, HEADER_H), (half_w, HEADER_H), C_RED, 2)
    _put(left_bgr, "BEFORE CODE FIX", 10, 28, scale=0.55, color=C_RED, thick=2)
    _put(left_bgr, f"A:{conf_a_b*100:.1f}%", half_w - 90, 28,
         scale=0.55, color=_score_color(conf_a_b), thick=2)

    # Right header
    cv2.rectangle(right_bgr, (0, 0), (half_w, HEADER_H), (18, 35, 18), -1)
    cv2.line(right_bgr, (0, HEADER_H), (half_w, HEADER_H), C_GREEN, 2)
    _put(right_bgr, "AFTER CODE FIX", 10, 28, scale=0.55, color=C_GREEN, thick=2)
    _put(right_bgr, f"Match:{match_score*100:.1f}%", half_w - 120, 28,
         scale=0.50, color=_score_color(match_score), thick=2)

    # Person labels on left (only A)
    if ref_l[5, 2] > 0.1:
        ax = min(max(int(ref_l[5, 0]) - 28, 4), half_w - 30)
        ay = max(int(ref_l[5, 1]) - 10, HEADER_H + 10)
        _put(left_bgr, "A", ax, ay, scale=0.55, color=C_RED, thick=2)

    # Person B NOT DETECTED badge on left
    _badge(left_bgr, 6, HEADER_H + 6, "Person B: NOT DETECTED", (60, 20, 20), C_RED)

    # Person labels on right (A and B)
    if ref_r[5, 2] > 0.1:
        ax = min(max(int(ref_r[5, 0]) - 28, 4), half_w - 30)
        ay = max(int(ref_r[5, 1]) - 10, HEADER_H + 10)
        _put(right_bgr, "A", ax, ay, scale=0.55, color=C_PERSON_A, thick=2)
    if b_detected and usr_r[5, 2] > 0.1:
        bx = min(max(int(usr_r[5, 0]) - 28, 4), half_w - 30)
        by = max(int(usr_r[5, 1]) - 10, HEADER_H + 10)
        _put(right_bgr, "B", bx, by, scale=0.55, color=C_PERSON_B, thick=2)

    # Face-guard badge on right
    fg_col  = C_GREEN if face_dir == "front" else C_YELLOW if face_dir == "side" else C_RED
    _badge(right_bgr, 6, HEADER_H + 6, f"Face Guard: ON  |  {face_dir.upper()}",
           (20, 55, 20), fg_col)
    if early:
        _badge(right_bgr, 6, HEADER_H + 32, "EARLY EXIT", (0, 90, 200), C_WHITE)

    # ── Assemble canvas ───────────────────────────────────────────────────
    cv2.line(left_bgr, (half_w - 1, 0), (half_w - 1, panel_h), C_WHITE, 2)
    canvas = np.zeros((out_h, out_w, 3), np.uint8)
    canvas[:panel_h] = np.hstack([left_bgr, right_bgr])
    cv2.line(canvas, (half_w, 0), (half_w, panel_h), C_WHITE, 2)

    # ── HUD ───────────────────────────────────────────────────────────────
    hud_y0 = out_h - HUD_H
    cv2.rectangle(canvas, (0, hud_y0), (out_w, out_h), (18, 18, 18), -1)
    cv2.line(canvas, (0,      hud_y0), (half_w, hud_y0), C_RED,   2)
    cv2.line(canvas, (half_w, hud_y0), (out_w,  hud_y0), C_GREEN, 2)

    margin = 10
    bar_w  = half_w - margin * 2
    bar_h2 = 16
    y      = hud_y0 + 10

    # Left HUD: Person A confidence bar + NOT DETECTED placeholder
    bw = int(conf_a_b * bar_w)
    cv2.rectangle(canvas, (margin, y), (margin + bar_w, y + bar_h2), (45, 45, 45), -1)
    cv2.rectangle(canvas, (margin, y), (margin + max(bw, 3), y + bar_h2),
                  _score_color(conf_a_b), -1)
    _put(canvas, f"Person A: {conf_a_b*100:.1f}%", margin + 4, y + bar_h2 - 2,
         scale=0.40, color=C_WHITE, thick=1, shadow=True)
    y_l = y + bar_h2 + 4

    cv2.rectangle(canvas, (margin, y_l), (margin + bar_w, y_l + bar_h2), (30, 20, 20), -1)
    cv2.rectangle(canvas, (margin, y_l), (margin + bar_w, y_l + bar_h2), C_RED, 1)
    _put(canvas, "Person B: NOT DETECTED", margin + 4, y_l + bar_h2 - 2,
         scale=0.40, color=C_RED, thick=1, shadow=False)
    y_l += bar_h2 + 4

    # Right HUD: Person A, Person B, Match bars
    y_r = hud_y0 + 10
    for label, conf, color in [
        ("Person A", conf_a_a, C_PERSON_A),
        ("Person B", conf_b_a, C_PERSON_B),
        ("A↔B Match", match_score, _score_color(match_score)),
    ]:
        aw = int(conf * bar_w)
        x0 = half_w + margin
        cv2.rectangle(canvas, (x0, y_r), (x0 + bar_w, y_r + bar_h2), (45, 45, 45), -1)
        cv2.rectangle(canvas, (x0, y_r), (x0 + max(aw, 3), y_r + bar_h2), color, -1)
        _put(canvas, f"{label}: {conf*100:.1f}%", x0 + 4, y_r + bar_h2 - 2,
             scale=0.40, color=C_WHITE, thick=1, shadow=True)
        y_r += bar_h2 + 4

    # Info row
    row2_y = max(y_l, y_r) + 4
    _put(canvas, f"Joints: {n_jts_b}/17  |  Single-Person Mode",
         margin, row2_y, scale=0.38, color=C_GRAY)
    _put(canvas, f"Joints: {n_jts_a}/17  |  Dual-Person + Face Guard",
         half_w + margin, row2_y, scale=0.38, color=C_GRAY)

    # Cumulative thin bars
    row3_y = row2_y + 18
    for x0, val in [(margin, cum_before), (half_w + margin, cum_match)]:
        if val > 0:
            cw = int(val * bar_w)
            cv2.rectangle(canvas, (x0, row3_y),
                          (x0 + max(cw, 3), row3_y + 4), _score_color(val), -1)
            _put(canvas, f"avg {val*100:.1f}%", x0, row3_y + 16,
                 scale=0.30, color=C_GRAY, thick=1, shadow=False)

    # Centre delta / detection badge
    if b_detected:
        d_txt = (f"DUAL DETECTION  |  A:{conf_a_a*100:.0f}%  "
                 f"B:{conf_b_a*100:.0f}%  Match:{match_score*100:.0f}%")
        d_col = _score_color(match_score)
    else:
        d_txt = "PERSON B: NOT IN FRAME  (single-person video)"
        d_col = C_GRAY

    delta_y = row3_y + 26
    (tw, _), _ = cv2.getTextSize(d_txt, FONT, 0.46, 2)
    dx  = (out_w - tw) // 2
    pad = 8
    cv2.rectangle(canvas, (dx - pad, delta_y - 16), (dx + tw + pad, delta_y + 6),
                  (35, 35, 35), -1)
    cv2.rectangle(canvas, (dx - pad, delta_y - 16), (dx + tw + pad, delta_y + 6), d_col, 1)
    _put(canvas, d_txt, dx, delta_y, scale=0.46, color=d_col, thick=2)

    # Legend
    legend_y = out_h - 8
    _put(canvas, f"Frame {frame_idx:04d}", 10, legend_y,
         scale=0.35, color=C_GRAY, thick=1, shadow=False)
    _put(canvas, "Cyan = Person A  |  Orange = Person B",
         half_w - 120, legend_y, scale=0.35, color=C_GRAY, thick=1, shadow=False)
    _put(canvas, f"Threshold {SIM_THRESHOLD:.0%}  Tolerance {JOINT_TOLERANCE}",
         out_w - 230, legend_y, scale=0.35, color=C_GRAY, thick=1, shadow=False)

    return canvas, conf_a_b, match_score


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _ffmpeg_available() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _open_writer(cmd, w, h):
    return subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _make_ffmpeg_cmd(out_path: str, w: int, h: int, fps: float) -> list:
    nvenc = False
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                           capture_output=True, text=True)
        nvenc = "h264_nvenc" in r.stdout
    except FileNotFoundError:
        pass
    codec = (["h264_nvenc", "-preset", "p4", "-cq", "22"]
             if nvenc else
             ["libx264", "-preset", "fast", "-crf", "22"])
    return [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "bgr24",
        "-r", str(fps), "-i", "pipe:0",
        "-c:v", *codec,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        out_path,
    ]


# ---------------------------------------------------------------------------
# Side-by-side only pipeline
# ---------------------------------------------------------------------------

def run_side_by_side(video_path: str, out_path: str):
    """Single output: Before (left) vs After (right) simultaneously."""
    if not _ffmpeg_available():
        sys.exit("ffmpeg not found.  Install ffmpeg and ensure it is on PATH.")

    poses_a, poses_b, frames, fps = extract_coco17_poses(video_path)
    n = len(frames)
    if n == 0:
        sys.exit("No frames extracted.")

    b_present = any(kps[:, 2].max() > 0.1 for kps in poses_b)
    if not b_present:
        print("Note: only 1 person detected — synthesising Person B for demo.")
        poses_b = make_user_poses(poses_a)

    src_h, src_w = frames[0].shape[:2]
    max_w = 540
    if src_w > max_w:
        sf      = max_w / src_w
        frames  = [cv2.resize(f, (max_w, int(src_h * sf))) for f in frames]
        for kps in poses_a:
            kps[:, 0] *= sf; kps[:, 1] *= sf
        for kps in poses_b:
            kps[:, 0] *= sf; kps[:, 1] *= sf
        src_h, src_w = frames[0].shape[:2]

    out_w = (src_w * 2) if (src_w * 2) % 2 == 0 else (src_w * 2 - 1)
    out_h = src_h + HUD_H
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    title_frames = make_title_card(out_w, out_h, fps, [
        ("BEFORE  vs  AFTER  — Dual Person Detection", 0.72, C_GOLD),
        ("Left: Single Person (old)  |  Right: Both Persons Detected (new)", 0.44, C_WHITE),
        ("Red = Before (1 person)  |  Cyan + Orange = After (2 persons)", 0.37, C_GRAY),
        ("Person A & B accuracy + cross-person match score displayed on right", 0.33, C_GRAY),
    ], C_GOLD, duration_sec=3.0)

    cmd  = _make_ffmpeg_cmd(out_path, out_w, out_h, fps)
    proc = _open_writer(cmd, out_w, out_h)

    for f in title_frames:
        proc.stdin.write(f.tobytes())

    hist_before, hist_match = [], []
    pbar = tqdm(total=n, desc="Rendering side-by-side", unit="frame")
    for i in range(n):
        cum_b = float(np.mean(hist_before)) if hist_before else 0.0
        cum_m = float(np.mean(hist_match))  if hist_match  else 0.0
        canvas, conf_a, match = render_split_frame(
            frames[i], poses_a[i], poses_b[i], i, out_w, out_h,
            cum_before=cum_b, cum_match=cum_m,
        )
        hist_before.append(conf_a)
        hist_match.append(match)
        try:
            proc.stdin.write(canvas.tobytes())
        except BrokenPipeError:
            break
        pbar.update(1)

    pbar.close()
    proc.stdin.close()
    proc.wait()

    print(f"\n{'='*56}")
    print(f"  Output             : {out_path}")
    print(f"  Frames             : {n}  @  {fps:.1f} fps")
    print(f"  Avg Person A conf  : {float(np.mean(hist_before))*100:.1f}%")
    print(f"  Avg A↔B Match score: {float(np.mean(hist_match))*100:.1f}%")
    print(f"{'='*56}")


# ---------------------------------------------------------------------------
# Main pipeline (3-part: Before + After + Compare merged)
# ---------------------------------------------------------------------------

def run(video_path: str, out_path: str):
    if not _ffmpeg_available():
        sys.exit("ffmpeg not found.  Install ffmpeg and ensure it is on PATH.")

    poses_a, poses_b, frames, fps = extract_coco17_poses(video_path)
    n = len(frames)
    if n == 0:
        sys.exit("No frames extracted from video.")

    b_present = any(kps[:, 2].max() > 0.1 for kps in poses_b)
    if not b_present:
        print("Note: only 1 person detected — synthesising Person B for demo.")
        poses_b = make_user_poses(poses_a)

    src_h, src_w = frames[0].shape[:2]
    max_w = 540
    if src_w > max_w:
        sf     = max_w / src_w
        new_h  = int(src_h * sf)
        frames = [cv2.resize(f, (max_w, new_h)) for f in frames]
        for kps in poses_a:
            kps[:, 0] *= sf; kps[:, 1] *= sf
        for kps in poses_b:
            kps[:, 0] *= sf; kps[:, 1] *= sf
        src_h, src_w = new_h, max_w

    out_h   = src_h + HUD_H
    out_w   = src_w
    split_w = (out_w * 2) if (out_w * 2) % 2 == 0 else (out_w * 2 - 1)
    split_h = out_h

    def _pad(img):
        return np.vstack([img, np.zeros((HUD_H, out_w, 3), np.uint8)])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    cmd_b  = _make_ffmpeg_cmd(out_path.replace(".mp4", "_before.mp4"),  out_w,   out_h,   fps)
    cmd_a  = _make_ffmpeg_cmd(out_path.replace(".mp4", "_after.mp4"),   out_w,   out_h,   fps)
    cmd_sp = _make_ffmpeg_cmd(out_path.replace(".mp4", "_compare.mp4"), split_w, split_h, fps)
    proc_b  = _open_writer(cmd_b,  out_w,   out_h)
    proc_a  = _open_writer(cmd_a,  out_w,   out_h)
    proc_sp = _open_writer(cmd_sp, split_w, split_h)

    for f in make_title_card(out_w, out_h, fps, [
        ("BEFORE MODIFICATION",                    0.88, C_RED),
        ("Single Person Detection  (Old Code)",    0.52, C_WHITE),
        ("Only Person A tracked  |  Person B invisible to system", 0.38, C_GRAY),
    ], C_RED, duration_sec=2.5):
        proc_b.stdin.write(f.tobytes())

    for f in make_title_card(out_w, out_h, fps, [
        ("AFTER MODIFICATION",                           0.88, C_GREEN),
        ("Dual Person Detection  (New Code)",            0.52, C_WHITE),
        ("Person A (Cyan)  +  Person B (Orange)  tracked simultaneously", 0.36, C_GRAY),
        ("Individual confidence + cross-person match score displayed",    0.33, C_GRAY),
    ], C_GREEN, duration_sec=2.5):
        proc_a.stdin.write(f.tobytes())

    for f in make_title_card(split_w, split_h, fps, [
        ("BEFORE  vs  AFTER",                                    0.92, C_GOLD),
        ("Side-by-Side: Single vs Dual Person Detection",        0.55, C_WHITE),
        ("Red = Before (1 person)  |  Cyan+Orange = After (2 persons)", 0.40, C_GRAY),
    ], C_GOLD, duration_sec=2.5):
        proc_sp.stdin.write(f.tobytes())

    scores_conf, scores_match = [], []
    pbar = tqdm(total=n, desc="Rendering comparison video", unit="frame")
    for i in range(n):
        bgr   = frames[i]
        kps_a = poses_a[i]
        kps_b = poses_b[i]

        panel_b = _pad(bgr)
        panel_b, conf_a = render_frame_before(panel_b, kps_a, i)
        scores_conf.append(conf_a)

        panel_a = _pad(bgr)
        panel_a, _, _, match = render_frame_after(panel_a, kps_a, kps_b, i)
        scores_match.append(match)

        split_frame, _, _ = render_split_frame(bgr, kps_a, kps_b, i, split_w, split_h)

        try:
            proc_b.stdin.write(panel_b.tobytes())
            proc_a.stdin.write(panel_a.tobytes())
            proc_sp.stdin.write(split_frame.tobytes())
        except BrokenPipeError:
            break
        pbar.update(1)

    pbar.close()
    for proc in [proc_b, proc_a, proc_sp]:
        proc.stdin.close()
        proc.wait()

    # Merge 3 parts into one file
    before_f       = out_path.replace(".mp4", "_before.mp4")
    after_f        = out_path.replace(".mp4", "_after.mp4")
    compare_f      = out_path.replace(".mp4", "_compare.mp4")
    compare_scaled = out_path.replace(".mp4", "_compare_scaled.mp4")
    concat_txt     = out_path.replace(".mp4", "_concat.txt")

    subprocess.run([
        "ffmpeg", "-y", "-i", compare_f,
        "-vf", f"scale={out_w}:{split_h}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p", compare_scaled,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with open(concat_txt, "w") as f:
        f.write(f"file '{Path(before_f).resolve()}'\n")
        f.write(f"file '{Path(after_f).resolve()}'\n")
        f.write(f"file '{Path(compare_scaled).resolve()}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_txt, "-c", "copy", out_path,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for tmp in [before_f, after_f, compare_f, compare_scaled, concat_txt]:
        try:
            Path(tmp).unlink()
        except FileNotFoundError:
            pass

    print(f"\n{'='*54}")
    print(f"  Output video            : {out_path}")
    print(f"  Frames                  : {n}")
    print(f"  Avg Person A confidence : {float(np.mean(scores_conf))*100:.1f}%")
    print(f"  Avg A↔B Match score    : {float(np.mean(scores_match))*100:.1f}%")
    print(f"{'='*54}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Generate Before/After dual-person detection comparison video")
    ap.add_argument("--video", required=True, help="Path to input video")
    ap.add_argument("--out",   default="output/compare_before_after.mp4",
                    help="Output video path")
    ap.add_argument("--mode",  default="full",
                    choices=["full", "side-by-side"],
                    help="'full' = 3-part sequential (default); "
                         "'side-by-side' = simultaneous left/right only")
    args = ap.parse_args()

    if not Path(args.video).exists():
        print(textwrap.dedent(f"""
            Video not found: {args.video}

            Download a YouTube Short first:
              yt-dlp "https://www.youtube.com/shorts/8XcXJIVjS28" -o data/shorts.mp4

            Then run:
              python -m metrics.accuracy.compare_video --video data/shorts.mp4 --mode side-by-side
        """))
        sys.exit(1)

    if args.mode == "side-by-side":
        default_out = "output/compare_side_by_side.mp4"
        out = args.out if args.out != "output/compare_before_after.mp4" else default_out
        run_side_by_side(args.video, out)
    else:
        run(args.video, args.out)


if __name__ == "__main__":
    main()
