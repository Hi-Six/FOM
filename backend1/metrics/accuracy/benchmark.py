# -*- coding: utf-8 -*-
"""
Accuracy scoring benchmark: Before vs After refactor.

Measures the wall-clock cost of per_joint_scores() across a synthetic
dataset that mirrors real user recordings:
  - Mix of good / bad alignment frames
  - Turned-face frames (face-occlusion test)
  - Structural-only early-exit frames

Output
------
  Terminal: comparison table (timing + similarity metrics)
  output/accuracy_benchmark.png: 4-panel chart

Usage
-----
  python -m metrics.accuracy.benchmark
  python -m metrics.accuracy.benchmark --frames 2000
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

# ---- Constants (mirror __init__.py) ----------------------------------------
JOINT_TOLERANCE      = 0.30
SIMILARITY_THRESHOLD = 0.65
L_EAR_IDX            = 3
R_EAR_IDX            = 4
FACE_OCCLUSION_VIS   = 0.30
FACE_JOINT_INDICES   = frozenset({0, 1, 2, 3, 4})
_STRUCT_JOINTS       = [5, 6, 11, 12]

JOINT_WEIGHTS = np.array([
    0.5, 0.3, 0.3, 0.2, 0.2,
    1.2, 1.2, 1.0, 1.0, 1.0, 1.0,
    1.2, 1.2, 1.0, 1.0, 1.0, 1.0,
], dtype=np.float32)

JOINT_NAMES = [
    "nose", "L.eye", "R.eye", "L.ear", "R.ear",
    "L.shl", "R.shl", "L.elb", "R.elb",
    "L.wri", "R.wri", "L.hip", "R.hip",
    "L.kne", "R.kne", "L.ank", "R.ank",
]


# ---- Synthetic pose generation ---------------------------------------------

def _rand_pose(
    rng: np.random.Generator,
    *,
    face_turned: bool = False,
) -> np.ndarray:
    """Return a random normalised (17, 3) pose [x, y, visibility]."""
    kps = rng.uniform(-1.5, 1.5, (17, 2)).astype(np.float32)
    vis = rng.uniform(0.6, 1.0, (17, 1)).astype(np.float32)
    for i in [5, 6, 11, 12]:       # structural anchors always visible
        vis[i] = 1.0
    if face_turned:
        vis[0] = rng.uniform(0.1, 0.35)
        vis[1] = rng.uniform(0.05, 0.20)
        vis[2] = rng.uniform(0.05, 0.20)
        vis[L_EAR_IDX] = rng.uniform(0.05, 0.20)
        vis[R_EAR_IDX] = rng.uniform(0.6, 1.0)
    return np.hstack([kps, vis])


def make_dataset(
    n: int,
    *,
    face_ratio: float = 0.30,
    bad_ratio:  float = 0.25,
    rng_seed:   int   = 42,
) -> list:
    """
    Generate n synthetic frame pairs tagged with their type:
      'good'     : high structural similarity (low noise)
      'bad'      : low structural similarity  -> triggers early-exit
      'face_turn': one pose has a turned face -> tests occlusion guard
    """
    rng   = np.random.default_rng(rng_seed)
    n_bad  = int(n * bad_ratio)
    n_face = int(n * face_ratio)
    n_good = n - n_bad - n_face
    frames = []

    def _pair(noise: float, face_turned: bool = False):
        ref = _rand_pose(rng, face_turned=False)
        usr = ref.copy()
        usr[:, :2] += rng.normal(0, noise, (17, 2)).astype(np.float32)
        if face_turned:
            usr = _rand_pose(rng, face_turned=True)
        return ref, usr

    for _ in range(n_good):
        frames.append((*_pair(0.08), "good"))
    for _ in range(n_bad):
        frames.append((*_pair(0.70), "bad"))
    for _ in range(n_face):
        frames.append((*_pair(0.10, face_turned=True), "face_turn"))

    rng.shuffle(frames)
    return frames


# ---- BEFORE: original loop-based implementation ----------------------------

def _normalize_pose_old(kps: np.ndarray):
    out     = kps.copy()
    visible = kps[:, 2] > 0
    if visible[11] and visible[12]:
        hip_mid = (kps[11, :2] + kps[12, :2]) / 2.0
    elif visible[11]:
        hip_mid = kps[11, :2]
    elif visible[12]:
        hip_mid = kps[12, :2]
    else:
        return None
    if visible[5] and visible[6]:
        shl_mid = (kps[5, :2] + kps[6, :2]) / 2.0
    elif visible[5]:
        shl_mid = kps[5, :2]
    elif visible[6]:
        shl_mid = kps[6, :2]
    else:
        return None
    torso_h = np.linalg.norm(shl_mid - hip_mid)
    if torso_h < 1e-6:
        return None
    out[:, :2] = (kps[:, :2] - hip_mid) / torso_h
    out[~visible, :2] = 0.0
    return out


def per_joint_scores_before(pa, pb) -> np.ndarray:
    """Original: Python loop, no face-occlusion guard, no early-exit."""
    na     = _normalize_pose_old(np.asarray(pa, dtype=np.float32))
    nb     = _normalize_pose_old(np.asarray(pb, dtype=np.float32))
    scores = np.full(17, np.nan, dtype=np.float32)
    if na is None or nb is None:
        return scores
    denom = 2.0 * JOINT_TOLERANCE ** 2
    for i in range(17):
        if na[i, 2] > 0.1 and nb[i, 2] > 0.1:
            d2 = float(((na[i, :2] - nb[i, :2]) ** 2).sum())
            scores[i] = np.exp(-d2 / denom)
    return scores


# ---- AFTER: from the refactored __init__.py --------------------------------

from metrics.accuracy import (
    normalize_pose,
    detect_face_direction,
    per_joint_scores as per_joint_scores_after,
)


# ---- Timing helper ---------------------------------------------------------

def _run_timed(fn, frames):
    scores, times = [], []
    for pa, pb, _ in frames:
        t0 = time.perf_counter()
        s  = fn(pa, pb)
        times.append((time.perf_counter() - t0) * 1000.0)
        scores.append(s)
    return scores, times


# ---- Aggregate similarity --------------------------------------------------

def _frame_similarity(scores: np.ndarray) -> float:
    vis = ~np.isnan(scores)
    if not vis.any():
        return 0.0
    return float(np.average(scores[vis], weights=JOINT_WEIGHTS[vis]))


def _similarity_stats(all_scores: list) -> dict:
    sims = [_frame_similarity(s) for s in all_scores]
    arr  = np.array(sims)
    return {
        "mean":   float(arr.mean()),
        "std":    float(arr.std()),
        "p25":    float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "p75":    float(np.percentile(arr, 75)),
        "above_threshold_pct": float((arr >= SIMILARITY_THRESHOLD).mean() * 100),
    }


# ---- Benchmark runner ------------------------------------------------------

def run_benchmark(n_frames: int = 1000) -> dict:
    frames = make_dataset(n_frames)

    print(f"\nRunning BEFORE ({n_frames} frames)...")
    scores_b, times_b = _run_timed(per_joint_scores_before, frames)

    print(f"Running AFTER  ({n_frames} frames)...")
    scores_a, times_a = _run_timed(per_joint_scores_after,  frames)

    tags = [f[2] for f in frames]
    early_exit_count = sum(
        1 for s in scores_a
        if np.count_nonzero(~np.isnan(s)) <= len(_STRUCT_JOINTS)
    )
    face_turn_count = sum(1 for t in tags if t == "face_turn")

    return {
        "n_frames":         n_frames,
        "tags":             tags,
        "times_before_ms":  times_b,
        "times_after_ms":   times_a,
        "scores_before":    scores_b,
        "scores_after":     scores_a,
        "early_exit_count": early_exit_count,
        "face_turn_count":  face_turn_count,
        "sim_before":       _similarity_stats(scores_b),
        "sim_after":        _similarity_stats(scores_a),
    }


# ---- Terminal table --------------------------------------------------------

def print_table(r: dict) -> None:
    tb = np.array(r["times_before_ms"])
    ta = np.array(r["times_after_ms"])
    sb = r["sim_before"]
    sa = r["sim_after"]
    reduction = (tb.mean() - ta.mean()) / tb.mean() * 100

    sep = "-" * 56
    print(f"\n{'ACCURACY SCORING - BEFORE vs AFTER':^56}")
    print(sep)
    print(f"{'Metric':<30} {'Before':>10} {'After':>10}")
    print(sep)
    print(f"{'Frames evaluated':<30} {r['n_frames']:>10,} {r['n_frames']:>10,}")
    print(f"{'Mean time/frame (ms)':<30} {tb.mean():>10.4f} {ta.mean():>10.4f}")
    print(f"{'Median time/frame (ms)':<30} {float(np.median(tb)):>10.4f} {float(np.median(ta)):>10.4f}")
    print(f"{'P95 time/frame (ms)':<30} {float(np.percentile(tb,95)):>10.4f} {float(np.percentile(ta,95)):>10.4f}")
    print(f"{'Total time (ms)':<30} {tb.sum():>10.2f} {ta.sum():>10.2f}")
    print(f"{'Speed-up (mean)':<30} {1.0:>10.2f}x {tb.mean()/ta.mean():>10.2f}x")
    print(f"{'Waiting-time reduction':<30} {'N/A':>10} {reduction:>9.1f}%")
    print(sep)
    print(f"{'Mean similarity score':<30} {sb['mean']:>10.4f} {sa['mean']:>10.4f}")
    print(f"{'Similarity std':<30} {sb['std']:>10.4f} {sa['std']:>10.4f}")
    print(f"{'Median similarity':<30} {sb['median']:>10.4f} {sa['median']:>10.4f}")
    print(f"{'Frames above threshold (%)':<30} {sb['above_threshold_pct']:>10.1f} {sa['above_threshold_pct']:>10.1f}")
    print(sep)
    print(f"{'Face-turn frames':<30} {r['face_turn_count']:>10,} {r['face_turn_count']:>10,}")
    print(f"{'Early-exit frames (after)':<30} {'N/A':>10} {r['early_exit_count']:>10,}")
    print(sep)

    print(f"\nPer-joint mean similarity  [After - Before]")
    print(f"  {'Joint':<10} {'Before':>8} {'After':>8} {'Delta':>8}")
    print(f"  {'-'*38}")
    for j, name in enumerate(JOINT_NAMES):
        b_vals = [s[j] for s in r["scores_before"] if not np.isnan(s[j])]
        a_vals = [s[j] for s in r["scores_after"]  if not np.isnan(s[j])]
        bm    = float(np.mean(b_vals)) if b_vals else float("nan")
        am    = float(np.mean(a_vals)) if a_vals else float("nan")
        delta = am - bm if not (np.isnan(bm) or np.isnan(am)) else float("nan")
        sign  = "+" if delta > 0 else ""
        print(f"  {name:<10} {bm:>8.4f} {am:>8.4f} {sign}{delta:>7.4f}")


# ---- Matplotlib chart ------------------------------------------------------

def plot_comparison(r: dict, out_path: Path) -> None:
    if not _HAS_MPL:
        print("\nmatplotlib not available -- skipping chart (pip install matplotlib)")
        return

    tb   = np.array(r["times_before_ms"])
    ta   = np.array(r["times_after_ms"])
    tags = np.array(r["tags"])

    sim_b = np.array([_frame_similarity(s) for s in r["scores_before"]])
    sim_a = np.array([_frame_similarity(s) for s in r["scores_after"]])

    fig = plt.figure(figsize=(14, 10))
    fig.suptitle("Accuracy Scoring: Before vs After Refactor", fontsize=14, fontweight="bold")
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.38, wspace=0.32)

    BLUE  = "#3B82F6"
    GREEN = "#22C55E"
    RED   = "#EF4444"

    # Panel 1: per-frame processing time (first 300 frames)
    ax1 = fig.add_subplot(gs[0, 0])
    x   = np.arange(min(len(tb), 300))
    ax1.plot(x, tb[:300], color=BLUE,  lw=0.8, alpha=0.7, label="Before")
    ax1.plot(x, ta[:300], color=GREEN, lw=0.8, alpha=0.7, label="After")
    ax1.set_title("Per-frame Processing Time (first 300 frames)")
    ax1.set_xlabel("Frame index")
    ax1.set_ylabel("Time (ms)")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    # Panel 2: waiting-time reduction bar chart
    ax2 = fig.add_subplot(gs[0, 1])
    categories  = ["All", "Good", "Bad", "Face-turn"]
    before_vals, after_vals = [], []
    for mask in [
        np.ones(len(tags), dtype=bool),
        tags == "good",
        tags == "bad",
        tags == "face_turn",
    ]:
        before_vals.append(float(tb[mask].mean()))
        after_vals.append(float(ta[mask].mean()))

    xpos  = np.arange(len(categories))
    width = 0.35
    bars_b = ax2.bar(xpos - width/2, before_vals, width, label="Before", color=BLUE,  alpha=0.85)
    bars_a = ax2.bar(xpos + width/2, after_vals,  width, label="After",  color=GREEN, alpha=0.85)

    for bb, ba in zip(bars_b, bars_a):
        pct = (bb.get_height() - ba.get_height()) / max(bb.get_height(), 1e-9) * 100
        ax2.text(
            ba.get_x() + ba.get_width() / 2,
            ba.get_height() + 0.0002,
            f"-{pct:.0f}%",
            ha="center", va="bottom", fontsize=7.5, color=RED, fontweight="bold",
        )

    ax2.set_title("Perceived Waiting-Time Reduction by Frame Type")
    ax2.set_ylabel("Mean processing time (ms)")
    ax2.set_xticks(xpos)
    ax2.set_xticklabels(categories, fontsize=9)
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3, axis="y")

    # Panel 3: similarity score distribution
    ax3 = fig.add_subplot(gs[1, 0])
    bins = np.linspace(0, 1, 40)
    ax3.hist(sim_b, bins=bins, color=BLUE,  alpha=0.65, label="Before", density=True)
    ax3.hist(sim_a, bins=bins, color=GREEN, alpha=0.65, label="After",  density=True)
    ax3.axvline(SIMILARITY_THRESHOLD, color=RED, lw=1.5, ls="--",
                label=f"Threshold ({SIMILARITY_THRESHOLD:.0%})")
    ax3.set_title("Similarity Score Distribution")
    ax3.set_xlabel("Frame similarity score")
    ax3.set_ylabel("Density")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    # Panel 4: per-joint mean similarity delta (After - Before)
    ax4 = fig.add_subplot(gs[1, 1])
    deltas = []
    for j in range(17):
        b_vals = [s[j] for s in r["scores_before"] if not np.isnan(s[j])]
        a_vals = [s[j] for s in r["scores_after"]  if not np.isnan(s[j])]
        bm = float(np.mean(b_vals)) if b_vals else 0.0
        am = float(np.mean(a_vals)) if a_vals else 0.0
        deltas.append(am - bm)

    colors_bar = [RED if d < 0 else GREEN for d in deltas]
    ax4.barh(JOINT_NAMES, deltas, color=colors_bar, alpha=0.85)
    ax4.axvline(0, color="gray", lw=0.8)
    ax4.set_title("Per-joint Similarity Delta (After - Before)")
    ax4.set_xlabel("Mean similarity change")
    ax4.grid(True, alpha=0.3, axis="x")
    ax4.tick_params(axis="y", labelsize=8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nChart saved -> {out_path}")


# ---- Entry point -----------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Accuracy scoring benchmark: before vs after")
    ap.add_argument("--frames", type=int, default=1000,
                    help="Number of synthetic frame pairs (default: 1000)")
    ap.add_argument("--out", default="output/accuracy_benchmark.png",
                    help="Output chart path")
    args = ap.parse_args()

    results = run_benchmark(n_frames=args.frames)
    print_table(results)
    plot_comparison(results, Path(args.out))


if __name__ == "__main__":
    main()
