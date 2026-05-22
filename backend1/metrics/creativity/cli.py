"""
창의성 점수 CLI — 영상 또는 이미지 쌍만 입력 (미디어 필수).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .extract import is_image_path
from .service import analyze_media_pair, ensure_output_dirs

_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
_DEFAULT_SAVE_DIR = _OUTPUT_ROOT / "extractions"
_DEFAULT_OUTPUT = _OUTPUT_ROOT / "creativity_score.json"


def default_output_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _OUTPUT_ROOT / f"creativity_score_{ts}.json"


def _require_file(path: str, label: str) -> Path:
    p = Path(path)
    if not p.is_file():
        print(f"{label} 파일이 없습니다: {path}", file=sys.stderr)
        raise SystemExit(1)
    return p


def _save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fmt_path(p: str) -> str:
    try:
        return str(Path(p).name)
    except Exception:
        return p


def _summarize_frame_diffs(frame_diffs: list[dict]) -> dict[str, float | int | None]:
    vals = [d["divergence"] for d in frame_diffs if d.get("divergence") is not None]
    skipped = sum(1 for d in frame_diffs if d.get("skipped"))
    if not vals:
        return {"count": 0, "skipped": skipped, "min": None, "max": None, "mean": None}
    return {
        "count": len(vals),
        "skipped": skipped,
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "mean": round(sum(vals) / len(vals), 4),
    }


def _print_report(
    payload: dict,
    *,
    out_path: Path,
    save_dir: Path,
) -> None:
    inputs = payload.get("inputs") or {}
    creativity = payload.get("creativity") or {}
    breakdown = creativity.get("breakdown") or {}
    accuracy = payload.get("accuracy") or {}
    acc_bd = accuracy.get("breakdown") or {}
    align = payload.get("alignment") or {}
    music = payload.get("music_align") or {}
    prep_user = (payload.get("preprocess") or {}).get("user") or {}
    prep_ref = (payload.get("preprocess") or {}).get("reference") or {}
    frame_diffs = creativity.get("frame_diffs") or []
    diff_summary = _summarize_frame_diffs(frame_diffs)

    lines: list[str] = []
    sep = "=" * 52

    lines.append(sep)
    lines.append("  창의성(Creativity) 분석 결과")
    lines.append(sep)
    lines.append("")
    lines.append(f"  창의성 점수: {creativity.get('score', 0):.2f} / 100")
    if accuracy:
        lines.append(f"  정확도 점수: {accuracy.get('score', 0):.2f} / 100 (참고)")
    lines.append("")
    lines.append("- 입력")
    lines.append(f"  사용자:     {_fmt_path(inputs.get('user', ''))}")
    lines.append(f"  레퍼런스:   {_fmt_path(inputs.get('reference', ''))}")
    lines.append(f"  미디어:     {inputs.get('media_type', '-')}")
    lines.append(f"  샘플 프레임: {inputs.get('num_frames', '-')}")
    if inputs.get("media_type") == "video":
        lines.append(f"  사용자 구간: {inputs.get('user_offset_sec', 0):.2f}s ~ {inputs.get('user_end_sec', '끝')}")
        lines.append(f"  레퍼 구간:   {inputs.get('ref_offset_sec', 0):.2f}s ~ {inputs.get('ref_end_sec', '끝')}")
        if inputs.get("music_align"):
            lines.append("  음악 정렬:   on (동일 BGM 전제)")
        elif inputs.get("auto_detect_start"):
            lines.append("  시작 추정:   auto-detect (포즈 움직임)")
    lines.append(f"  정렬 방식:   {inputs.get('alignment', '-')}")
    lines.append(f"  미러 보정:   {inputs.get('apply_mirror', '-')}")
    if music and not music.get("error"):
        lines.append("")
        lines.append("- 음악 구간 (크로마)")
        lines.append(
            f"  공통 길이: {music.get('common_duration_sec', '-')}s  "
            f"매칭 peak: {music.get('music_match_peak', '-')}  "
            f"연속성: {music.get('music_continuity', '-')}"
        )
        if music.get("music_verified") is not None:
            ok = "예" if music.get("music_verified") else "아니오"
            lines.append(f"  검증 통과: {ok}")
    elif music and music.get("error"):
        lines.append("")
        lines.append(f"- 음악 정렬 실패: {music['error']}")
    lines.append("")
    lines.append("- 전처리")
    for label, prep in (("사용자", prep_user), ("레퍼런스", prep_ref)):
        if not prep:
            continue
        end_s = prep.get("end_sec")
        end_txt = f"{end_s:.2f}s" if end_s is not None else "끝"
        lines.append(
            f"  [{label}] {prep.get('offset_sec', 0):.2f}s~{end_txt} | "
            f"전체 {prep.get('frames_total', '?')} → "
            f"샘플 {prep.get('frames_after_sample', '?')} → "
            f"유효 {prep.get('frames_after_visibility', '?')}"
        )
        mirror = "적용" if prep.get("mirror_applied") else "없음"
        lines.append(f"         미러 {mirror}, 중앙점수 {prep.get('avg_main_dancer_center_score', '-')}")
    lines.append("")
    lines.append("- 프레임 정렬")
    lines.append(f"  방식: {align.get('method', '-')}, 쌍 {align.get('pair_count', 0)}개")
    if align.get("dtw_mean_cost") is not None:
        lines.append(f"  DTW 평균 비용: {align.get('dtw_mean_cost')}")
    dup = align.get("duplicate_ref_ratio")
    if dup is not None:
        lines.append(f"  레퍼 중복 매칭 비율: {float(dup) * 100:.1f}%")
    if align.get("warning"):
        lines.append(f"  경고: {align['warning']}")
    lines.append("")
    lines.append("- 점수 구성 (breakdown)")
    if breakdown.get("reason"):
        lines.append(f"  사유: {breakdown['reason']}")
    else:
        lines.append(f"  평균 이탈(mean_divergence):  {breakdown.get('mean_divergence', 0):.4f}")
        lines.append(f"  band factor:               {breakdown.get('divergence_band_factor', '-')}")
        lines.append(f"  DTW penalty:               {breakdown.get('dtw_penalty_factor', '-')}")
        lines.append(f"  effective band:            {breakdown.get('effective_band_factor', '-')}")
        lines.append(f"  combined_raw:                {breakdown.get('combined_raw', '-')}")
        if breakdown.get("baseline_subtracted"):
            lines.append(f"  baseline_raw:                {breakdown.get('baseline_combined_raw', '-')}")
            lines.append(f"  after baseline:              {breakdown.get('combined_after_baseline', '-')}")
        lines.append(
            f"  평가 쌍: {breakdown.get('pairs_used', 0)} / {breakdown.get('pairs_evaluated', 0)}"
        )
    if acc_bd and not acc_bd.get("reason"):
        lines.append("")
        lines.append("- 정확도 (참고)")
        lines.append(f"  similarity_factor: {acc_bd.get('similarity_factor', '-')}")
        if acc_bd.get("reference_self_score") is not None:
            lines.append(f"  ref vs ref:        {acc_bd.get('reference_self_score')}점")
    lines.append("")
    lines.append("- 프레임별 이탈 요약")
    if diff_summary["count"]:
        lines.append(
            f"  {diff_summary['count']}프레임  "
            f"min {diff_summary['min']}  max {diff_summary['max']}  mean {diff_summary['mean']}"
        )
        if diff_summary["skipped"]:
            lines.append(f"  스킵: {diff_summary['skipped']}프레임")

        def _diff_line(d: dict) -> str:
            uf, rf = d.get("user_frame", "?"), d.get("ref_frame", "?")
            div = d.get("divergence")
            if div is None:
                return f"  user#{uf} <-> ref#{rf}  (스킵)"
            return f"  user#{uf} <-> ref#{rf}  divergence {div:.4f}"

        if len(frame_diffs) <= 8:
            for d in frame_diffs:
                lines.append(_diff_line(d))
        else:
            for d in frame_diffs[:3]:
                lines.append(_diff_line(d))
            lines.append(f"  ... ({len(frame_diffs) - 5}프레임 생략)")
            for d in frame_diffs[-2:]:
                lines.append(_diff_line(d))
    else:
        lines.append("  (비교 가능한 프레임 없음)")
    lines.append("")
    lines.append("- 저장 파일")
    lines.append(f"  결과 JSON: {out_path}")
    lines.append(f"  추출 JSON: {save_dir}")
    lines.append(sep)

    print("\n".join(lines))


def cmd_run(args: argparse.Namespace) -> int:
    user_path = _require_file(args.user, "사용자")
    ref_path = _require_file(args.reference, "레퍼런스")

    user_is_image = is_image_path(user_path)
    ref_is_image = is_image_path(ref_path)
    if user_is_image != ref_is_image:
        print(
            "사용자·레퍼런스는 둘 다 영상이거나 둘 다 이미지여야 합니다.",
            file=sys.stderr,
        )
        return 1

    save_dir = Path(args.save_dir) if args.save_dir else _DEFAULT_SAVE_DIR
    try:
        payload = analyze_media_pair(
            user_path,
            ref_path,
            num_frames=args.num_frames,
            user_offset_sec=args.user_offset,
            ref_offset_sec=args.ref_offset,
            auto_detect_start=args.auto_detect_start,
            music_align=args.music_align,
            baseline=args.baseline,
            with_accuracy=args.with_accuracy,
            alignment=args.alignment,
            apply_mirror=args.apply_mirror,
            visibility_threshold=args.visibility_threshold,
            save_extractions=True,
            save_dir=save_dir,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    align_meta = payload.get("alignment") or {}
    if align_meta.get("warning"):
        print(align_meta["warning"], file=sys.stderr)

    out_path = Path(args.output) if args.output else default_output_path()
    _save_json(payload, out_path)

    if args.json_stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_report(payload, out_path=out_path, save_dir=save_dir)
        print(f"\n상세 JSON: {out_path}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="창의성(creativity): 영상/이미지 쌍 비교 후 점수 산출 (미디어 필수)",
    )
    parser.add_argument("--user", required=True, help="사용자 영상 또는 이미지")
    parser.add_argument("--reference", required=True, help="레퍼런스 영상 또는 이미지")
    parser.add_argument(
        "--num-frames",
        type=int,
        default=50,
        metavar="N",
        help="음악 구간(또는 offset 이후)에서 균등 샘플 프레임 수 (기본 50)",
    )
    parser.add_argument(
        "--user-offset",
        type=float,
        default=0.0,
        help="사용자 샘플 시작(초). 0이 아니면 음악 정렬 스킵",
    )
    parser.add_argument(
        "--ref-offset",
        type=float,
        default=0.0,
        help="레퍼런스 샘플 시작(초). 0이 아니면 음악 정렬 스킵",
    )
    parser.add_argument(
        "--auto-detect-start",
        action="store_true",
        help="포즈 움직임으로 춤 시작 추정 (음악 정렬과 동시 사용 불가)",
    )
    parser.add_argument(
        "--music-align",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="동일 BGM 전제 크로마 구간 [시작,끝] 정렬 후 샘플 (기본 on)",
    )
    parser.add_argument(
        "--baseline",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="ref vs ref 기준선 보정 (기본 on)",
    )
    parser.add_argument(
        "--with-accuracy",
        action="store_true",
        help="동일 파이프라인 정확도 점수 함께 출력",
    )
    parser.add_argument(
        "--alignment",
        choices=("index", "time", "dtw"),
        default="dtw",
        help="프레임 정렬: index, time, dtw (기본 dtw)",
    )
    parser.add_argument(
        "--apply-mirror",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="좌우 미러 감지 시 관절 left/right 스왑",
    )
    parser.add_argument(
        "--visibility-threshold",
        type=float,
        default=0.5,
        help="핵심 관절 visibility 최소값",
    )
    parser.add_argument("-o", "--output", default=None, help="결과 JSON 경로")
    parser.add_argument(
        "--json",
        dest="json_stdout",
        action="store_true",
        help="터미널에 전체 JSON 출력 (기본: 요약만 출력)",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        help="추출 JSON 저장 폴더 (기본: output/extractions/)",
    )

    args = parser.parse_args(argv)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
