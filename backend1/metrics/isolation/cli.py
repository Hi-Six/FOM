"""Isolation 로컬 CLI — download · track · extract · align · score · run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND1 = Path(__file__).resolve().parents[2]
if str(_BACKEND1) not in sys.path:
    sys.path.insert(0, str(_BACKEND1))

from metrics.isolation.align.time_align import align_and_save
from metrics.isolation.config import DATA_ARTIFACTS, DATA_RAW, REF_VIDEO_NAME
from metrics.isolation.pipeline.extract import extract_and_save
from metrics.isolation.pipeline.io import save_json
from metrics.isolation.pipeline.tracker import PersonTracker
from metrics.isolation.score import (
    score_from_alignment,
    score_from_paths,
    score_isolation,
)


def cmd_download(args: argparse.Namespace) -> None:
    from metrics.isolation.scripts.download_videos import download
    from metrics.isolation.config import REF_VIDEO_URL

    ref_path = DATA_RAW / REF_VIDEO_NAME
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[ref] {args.ref_url or REF_VIDEO_URL}")
    download(args.ref_url or REF_VIDEO_URL, ref_path)
    print(f"  → {ref_path.resolve()}")

    if args.user_url:
        from metrics.isolation.scripts.download_videos import download as dl

        user_path = DATA_RAW / "user.mp4"
        print(f"[user] {args.user_url}")
        dl(args.user_url, user_path)
        print(f"  → {user_path.resolve()}")


def cmd_track(args: argparse.Namespace) -> None:
    video = Path(args.video)
    if not video.is_file():
        print(f"영상 없음: {video}", file=sys.stderr)
        sys.exit(1)

    try:
        tracker = PersonTracker(
            model_name=args.model,
            padding_ratio=args.padding,
            device=args.device,
            vid_stride=args.vid_stride,
        )
    except ImportError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"tracking: {video} (stride={args.vid_stride}, device={args.device or 'auto'})")
    frames = tracker.track_all(video)
    print(f"video: {video}")
    print(f"tracked frames: {len(frames)}")
    if frames:
        print(
            f"  first bbox: {frames[0].bbox_xyxy} "
            f"track_id={frames[0].track_id} conf={frames[0].confidence:.2f}"
        )
        print(
            f"  last  bbox: {frames[-1].bbox_xyxy} "
            f"track_id={frames[-1].track_id} conf={frames[-1].confidence:.2f}"
        )

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "frame_index": f.frame_index,
                "time_sec": f.time_sec,
                "bbox_xyxy": list(f.bbox_xyxy),
                "track_id": f.track_id,
                "confidence": f.confidence,
                "frame_width": f.frame_width,
                "frame_height": f.frame_height,
            }
            for f in frames
        ]
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  saved: {out.resolve()}")


def cmd_extract(args: argparse.Namespace) -> None:
    video = Path(args.video)
    if not video.is_file():
        print(f"영상 없음: {video}", file=sys.stderr)
        sys.exit(1)

    out = Path(args.out)
    tracks_path = Path(args.tracks) if args.tracks else None
    if tracks_path and not tracks_path.is_file():
        print(f"tracks JSON 없음: {tracks_path}", file=sys.stderr)
        sys.exit(1)

    print(f"extract: {video}")
    if tracks_path:
        print(f"  tracks: {tracks_path} (YOLO 생략)")
    elif args.no_tracks_cache:
        print("  tracks: YOLO 재실행")
    else:
        default_tracks = DATA_ARTIFACTS / "ref_tracks.json"
        if video.resolve() == (DATA_RAW / REF_VIDEO_NAME).resolve() and default_tracks.is_file():
            tracks_path = default_tracks
            print(f"  tracks: {tracks_path} (자동)")

    data = extract_and_save(
        video,
        out,
        tracks_json_path=tracks_path,
        reuse_yolo=not args.no_tracks_cache,
        progress_every=args.progress_every,
        device=args.device,
        vid_stride=1,
    )
    n = len(data.get("frames", []))
    print(f"  frames: {n}")
    print(f"  saved: {out.resolve()}")


def cmd_align(args: argparse.Namespace) -> None:
    user_json = Path(args.user)
    ref_json = Path(args.ref)
    for p in (user_json, ref_json):
        if not p.is_file():
            print(f"JSON 없음: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"align: user={user_json.name} ref={ref_json.name}")
    result = align_and_save(
        user_json,
        ref_json,
        Path(args.out),
        user_offset_sec=args.user_offset,
        ref_offset_sec=args.ref_offset,
        auto_detect_start=args.auto_detect_start,
    )
    align_meta = result["alignment"]
    print(f"  pairs: {align_meta['pair_count']}")
    print(f"  offsets: user={align_meta['user_offset_sec']}s ref={align_meta['ref_offset_sec']}s")
    if align_meta.get("warning"):
        print(f"  warning: {align_meta['warning']}")
    print(f"  saved: {Path(args.out).resolve()}")


def cmd_score(args: argparse.Namespace) -> None:
    if args.pairs:
        pairs_path = Path(args.pairs)
        if not pairs_path.is_file():
            print(f"없음: {pairs_path}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(pairs_path.read_text(encoding="utf-8"))
        pairs = data.get("pairs", data if isinstance(data, list) else [])
        result = score_isolation(pairs)
        if isinstance(data, dict) and "alignment" in data:
            result["alignment"] = data["alignment"]
    else:
        user_json = Path(args.user)
        ref_json = Path(args.ref)
        for p in (user_json, ref_json):
            if not p.is_file():
                print(f"JSON 없음: {p}", file=sys.stderr)
                sys.exit(1)
        print(f"score: user={user_json.name} ref={ref_json.name}")
        result = score_from_paths(
            str(user_json),
            str(ref_json),
            aligned_out=str(args.aligned_out) if args.aligned_out else None,
            score_out=str(args.out) if args.out else None,
            user_offset_sec=args.user_offset,
            ref_offset_sec=args.ref_offset,
            auto_detect_start=args.auto_detect_start,
        )

    print(f"  isolation score: {result['score']}")
    bd = result.get("breakdown", {})
    if bd.get("mean_user_coupling") is not None:
        print(
            f"  coupling  user={bd.get('mean_user_coupling')} "
            f"ref={bd.get('mean_ref_coupling')}"
        )
    if args.out and args.pairs:
        save_json(result, args.out)
        print(f"  saved: {Path(args.out).resolve()}")
    elif args.out and not args.pairs:
        print(f"  saved: {Path(args.out).resolve()}")


def cmd_run(args: argparse.Namespace) -> None:
    """user mp4 → (tracks) → extract → align → score 한 번에."""
    user_video = Path(args.user_video)
    ref_json = Path(args.ref_json)
    user_json = Path(args.user_json)
    user_tracks = Path(args.user_tracks) if args.user_tracks else DATA_ARTIFACTS / "user_tracks.json"

    if not ref_json.is_file():
        print(f"기준 JSON 없음: {ref_json} (먼저 extract ref)", file=sys.stderr)
        sys.exit(1)
    if not user_video.is_file():
        print(f"사용자 영상 없음: {user_video}", file=sys.stderr)
        sys.exit(1)

    if args.skip_extract and not user_json.is_file():
        print(f"user JSON 없음: {user_json}", file=sys.stderr)
        sys.exit(1)

    if not args.skip_extract:
        print("=== extract user ===")
        tracks_arg = user_tracks if user_tracks.is_file() else None
        extract_and_save(
            user_video,
            user_json,
            tracks_json_path=tracks_arg,
            reuse_yolo=True,
            progress_every=args.progress_every,
            device=args.device,
        )
        print(f"  → {user_json}")

    aligned_path = Path(args.aligned_out)
    score_path = Path(args.score_out)

    print("=== align ===")
    align_and_save(
        user_json,
        ref_json,
        aligned_path,
        user_offset_sec=args.user_offset,
        ref_offset_sec=args.ref_offset,
        auto_detect_start=args.auto_detect_start,
    )
    print(f"  → {aligned_path}")

    print("=== score ===")
    aligned_data = json.loads(aligned_path.read_text(encoding="utf-8"))
    result = score_from_alignment(aligned_data)
    save_json(result, score_path)

    print(f"  isolation score: {result['score']}")
    print(f"  → {score_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="isolation 로컬 검증 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download", help="기준(·user) 영상 다운로드")
    p_dl.add_argument("--ref-url", default=None)
    p_dl.add_argument("--user-url", default=None)
    p_dl.set_defaults(func=cmd_download)

    p_tr = sub.add_parser("track", help="YOLO11 트래킹")
    p_tr.add_argument("--video", type=Path, default=DATA_RAW / REF_VIDEO_NAME)
    p_tr.add_argument("--model", default="yolo11n.pt")
    p_tr.add_argument("--padding", type=float, default=0.0)
    p_tr.add_argument("--device", default=None)
    p_tr.add_argument("--vid-stride", type=int, default=1)
    p_tr.add_argument("--out", type=Path, default=None)
    p_tr.set_defaults(func=cmd_track)

    p_ex = sub.add_parser("extract", help="YOLO crop + MediaPipe Heavy → JSON")
    p_ex.add_argument("--video", type=Path, default=DATA_RAW / REF_VIDEO_NAME)
    p_ex.add_argument("--out", type=Path, default=DATA_ARTIFACTS / "ref.json")
    p_ex.add_argument("--tracks", type=Path, default=None)
    p_ex.add_argument("--no-tracks-cache", action="store_true")
    p_ex.add_argument("--device", default=None)
    p_ex.add_argument("--progress-every", type=int, default=50)
    p_ex.set_defaults(func=cmd_extract)

    def _add_align_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--user-offset", type=float, default=0.0)
        p.add_argument("--ref-offset", type=float, default=0.0)
        p.add_argument("--auto-detect-start", action="store_true")

    p_al = sub.add_parser("align", help="time 정렬 → aligned_pairs JSON")
    p_al.add_argument("--user", type=Path, required=True)
    p_al.add_argument("--ref", type=Path, default=DATA_ARTIFACTS / "ref.json")
    p_al.add_argument("--out", type=Path, default=DATA_ARTIFACTS / "aligned_pairs.json")
    _add_align_flags(p_al)
    p_al.set_defaults(func=cmd_align)

    p_sc = sub.add_parser("score", help="isolation 채점")
    p_sc.add_argument("--pairs", type=Path, default=None, help="aligned JSON")
    p_sc.add_argument("--user", type=Path, default=DATA_ARTIFACTS / "user.json")
    p_sc.add_argument("--ref", type=Path, default=DATA_ARTIFACTS / "ref.json")
    p_sc.add_argument("--aligned-out", type=Path, default=None)
    p_sc.add_argument("--out", type=Path, default=DATA_ARTIFACTS / "isolation_score.json")
    _add_align_flags(p_sc)
    p_sc.set_defaults(func=cmd_score)

    p_run = sub.add_parser("run", help="user 영상 전체 파이프라인")
    p_run.add_argument("--user-video", type=Path, default=DATA_RAW / "user.mp4")
    p_run.add_argument("--ref-json", type=Path, default=DATA_ARTIFACTS / "ref.json")
    p_run.add_argument("--user-json", type=Path, default=DATA_ARTIFACTS / "user.json")
    p_run.add_argument("--user-tracks", type=Path, default=None)
    p_run.add_argument("--aligned-out", type=Path, default=DATA_ARTIFACTS / "aligned_pairs.json")
    p_run.add_argument("--score-out", type=Path, default=DATA_ARTIFACTS / "isolation_score.json")
    p_run.add_argument("--skip-extract", action="store_true")
    p_run.add_argument("--device", default=None)
    p_run.add_argument("--progress-every", type=int, default=50)
    _add_align_flags(p_run)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
