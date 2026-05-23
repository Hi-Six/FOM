"""
ref 패널 — pause vs activation 구간 검출 수 비교 (2people1~7).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND1 = Path(__file__).resolve().parents[3]
if str(_BACKEND1) not in sys.path:
    sys.path.insert(0, str(_BACKEND1))

from metrics.creativity.activation_segment import (
    detect_activation_boundaries_and_segments,
)
from metrics.creativity.pause_detect import detect_pauses_and_motion_segments
from metrics.creativity.service import _resolve_video_windows
from metrics.creativity.split_screen_extract import extract_split_screen_video

DESKTOP = Path(r"C:\Users\804\Desktop")


def main() -> None:
    indices = list(range(1, 8))
    rows: list[dict] = []

    print(
        f"{'영상':<14} {'pause구간':>10} {'pause경계':>10} "
        f"{'act구간':>10} {'act경계':>10} {'윈도우초':>12}"
    )
    print("-" * 70)

    for i in indices:
        video = DESKTOP / f"2people{i}.mp4"
        if not video.is_file():
            print(f"{video.name:<14}  (파일 없음)")
            continue

        print(f"{video.name} 추출...", flush=True)
        user_raw, ref_raw, _meta = extract_split_screen_video(str(video))
        _u0, _u1, ref_offset, ref_end, _music, _use = _resolve_video_windows(
            video,
            video,
            user_raw,
            ref_raw,
            music_align=True,
            user_offset_sec=0.0,
            ref_offset_sec=0.0,
            auto_detect_start=False,
        )
        if ref_end is None:
            ref_end = max(
                float(f.get("time_sec", 0.0)) for f in ref_raw.get("frames") or []
            )
        ref_frames = ref_raw.get("frames") or []

        pause_data = detect_pauses_and_motion_segments(
            ref_frames,
            window_start_sec=ref_offset,
            window_end_sec=ref_end,
            pause_tuning_level=0,
        )
        act_data = detect_activation_boundaries_and_segments(
            ref_frames,
            window_start_sec=ref_offset,
            window_end_sec=ref_end,
        )

        p_seg = pause_data.get("motion_segment_count") or 0
        p_bnd = pause_data.get("pause_count") or 0
        a_seg = act_data.get("motion_segment_count") or 0
        a_bnd = act_data.get("boundary_count") or 0
        win = f"{ref_offset:.1f}-{ref_end:.1f}"

        rows.append(
            {
                "video": video.name,
                "window_sec": [ref_offset, ref_end],
                "pause_segments": p_seg,
                "pause_boundaries": p_bnd,
                "activation_segments": a_seg,
                "activation_boundaries": a_bnd,
                "activation_threshold": act_data.get("activation_threshold"),
            }
        )
        print(
            f"{video.name:<14} {p_seg:>10} {p_bnd:>10} {a_seg:>10} {a_bnd:>10} {win:>12}"
        )

    out = (
        Path(__file__).resolve().parent.parent
        / "output"
        / "activation_segment_2people_1-7.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"results": rows}, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
