"""
멈춤 튜닝 0~5 누적 단계 — 분할 화면 영상 배치 테스트.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND1 = Path(__file__).resolve().parents[3]
if str(_BACKEND1) not in sys.path:
    sys.path.insert(0, str(_BACKEND1))

from metrics.creativity.service import analyze_extraction_pair
from metrics.creativity.split_screen_extract import extract_split_screen_video

DESKTOP = Path(r"C:\Users\804\Desktop")
LEVEL_LABELS = {
    0: "기본",
    1: "+1 임계값 완화",
    2: "+2 연속저속·진입완화",
    3: "+3 병합·최소구간 축소",
    4: "+4 t_low 추가 상향",
    5: "+5 멈춤매칭·스킵 완화",
}


def run_video(video: Path) -> list[dict]:
    print(f"\n{'='*60}\n추출: {video.name}", flush=True)
    user_raw, ref_raw, meta = extract_split_screen_video(str(video))
    rows: list[dict] = []
    for level in range(6):
        print(f"  level {level} ...", flush=True)
        payload = analyze_extraction_pair(
            user_raw,
            ref_raw,
            user_source=str(video),
            ref_source=str(video),
            music_align=True,
            alignment="index",
            analysis_mode="both",
            save_extractions=False,
            pause_tuning_level=level,
            extra_inputs={
                "mode": "split_screen",
                "split_ratio": meta.get("split_ratio", 0.5),
                "left_role": meta.get("left_role", "user"),
            },
        )
        motion = payload.get("motion") or {}
        bd = motion.get("breakdown") or {}
        ref_pd = motion.get("ref_pause_detection") or {}
        rows.append(
            {
                "level": level,
                "label": LEVEL_LABELS[level],
                "detected": ref_pd.get("motion_segment_count"),
                "scored": bd.get("scored_segment_count"),
                "skipped": bd.get("skipped_segment_count"),
                "pause_count": ref_pd.get("pause_count"),
                "motion_score": motion.get("score"),
                "total_score": (payload.get("creativity") or {}).get("score"),
                "t_low": ref_pd.get("velocity_threshold_low"),
                "t_high": ref_pd.get("velocity_threshold_high"),
            }
        )
    return rows


def print_table(name: str, rows: list[dict]) -> None:
    print(f"\n[{name}]  검출/채점/스킵/멈춤 | 동작·종합")
    print(f"{'Lv':<3} {'검출':>4} {'채점':>4} {'스킵':>4} {'멈춤':>4} {'동작':>7} {'종합':>7}")
    print("-" * 42)
    for r in rows:
        print(
            f"L{r['level']:<2} {r['detected'] or 0:>4} {r['scored'] or 0:>4} "
            f"{r['skipped'] or 0:>4} {r['pause_count'] or 0:>4} "
            f"{r['motion_score'] or 0:>7.2f} {r['total_score'] or 0:>7.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "indices",
        nargs="*",
        type=int,
        default=list(range(1, 8)),
        help="영상 번호 (기본 1-7)",
    )
    args = parser.parse_args()

    all_results: dict[str, object] = {"videos": {}}
    missing: list[str] = []

    for i in args.indices:
        video = DESKTOP / f"2people{i}.mp4"
        if not video.is_file():
            missing.append(video.name)
            continue
        rows = run_video(video)
        all_results["videos"][video.name] = {
            "path": str(video),
            "results": rows,
        }
        print_table(video.name, rows)

    out = (
        Path(__file__).resolve().parent.parent
        / "output"
        / f"pause_tuning_2people_{'-'.join(str(x) for x in args.indices)}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    if missing:
        print(f"\n없는 파일: {', '.join(missing)}")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
