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
from .split_screen_service import analyze_split_screen_video

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


def _fmt_times(times: list[float] | None, *, limit: int = 16) -> str:
    if not times:
        return "(없음)"
    parts = [f"{float(t):.2f}s" for t in times[:limit]]
    if len(times) > limit:
        parts.append(f"...+{len(times) - limit}")
    return ", ".join(parts)


def _append_motion_scoring_detail(lines: list[str], motion: dict | None) -> None:
    """동작 측면 boundary 채점 — 구분·매칭·중간구분·과정."""
    if not motion:
        return
    bd = motion.get("breakdown") or {}
    summary = motion.get("scoring_summary") or {}
    mode = bd.get("scoring_mode") or bd.get("motion_scoring") or "-"

    ref_det = motion.get("ref_pause_detection") or {}
    user_det = motion.get("user_pause_detection") or {}

    ref_seg_n = summary.get("ref_segment_count", ref_det.get("motion_segment_count", "-"))
    user_seg_n = summary.get(
        "user_segment_count", user_det.get("motion_segment_count", "-")
    )

    lines.append("")
    lines.append("- 동작 측면 상세 (구분·매칭·채점)")
    lines.append(f"  채점 방식:     {mode}")
    lines.append(
        f"  ref 구간 수:   {ref_seg_n}  |  user 구간 수: {user_seg_n}"
    )
    lines.append(
        f"  ref 내부 구분: {summary.get('ref_boundary_instant_count', len(ref_det.get('pause_instants_sec') or []))}개  "
        f"|  user 내부 구분: {summary.get('user_boundary_instant_count', len(user_det.get('pause_instants_sec') or []))}개"
    )

    matched = summary.get("matched_boundaries_sec")
    if matched is None:
        matched = [
            m["ref_sec"]
            for m in (summary.get("boundary_matching") or [])
            if m.get("matched")
        ]
    lines.append(f"  매칭된 ref 구분점: {_fmt_times(matched)}")

    ref_points = (
        summary.get("ref_boundary_points")
        or summary.get("boundary_matching")
        or []
    )
    user_points = summary.get("user_boundary_points") or []
    if not user_points and motion.get("user_boundary_times_sec"):
        user_points = [
            {"user_sec": t, "ref_sec": None, "matched": False, "delta_sec": None}
            for t in (motion.get("user_boundary_times_sec") or [])
        ]
    if not ref_points and motion.get("ref_boundary_times_sec"):
        ref_points = [
            {"ref_sec": t, "user_sec": None, "matched": False, "delta_sec": None}
            for t in (motion.get("ref_boundary_times_sec") or [])
        ]

    if ref_points:
        lines.append(f"  ref 구분점 전체 ({len(ref_points)}개):")
        for m in ref_points:
            mark = "O" if m.get("matched") else "X"
            us = m.get("user_sec")
            us_txt = f"{us:.2f}s" if us is not None else "-"
            d = m.get("delta_sec")
            d_txt = f"  Δ{d:.3f}s" if d is not None else ""
            lines.append(
                f"    [{mark}] ref {m.get('ref_sec')}s → user {us_txt}{d_txt}"
            )

    if user_points:
        lines.append(f"  user 구분점 전체 ({len(user_points)}개):")
        for m in user_points:
            mark = "O" if m.get("matched") else "X"
            rs = m.get("ref_sec")
            rs_txt = f"{rs:.2f}s" if rs is not None else "-"
            d = m.get("delta_sec")
            d_txt = f"  Δ{d:.3f}s" if d is not None else ""
            lines.append(
                f"    [{mark}] user {m.get('user_sec')}s → ref {rs_txt}{d_txt}"
            )

    interiors = summary.get("interior_boundaries_sec") or []
    lines.append(
        f"  user 사이 구분:  {summary.get('interior_boundary_count', len(interiors))}개  "
        f"[{_fmt_times(interiors)}]"
    )

    pause_match = motion.get("pause_match") or {}
    if pause_match:
        lines.append("  ref 내부 구분 ↔ user (pause_match):")
        for k in sorted(pause_match.keys(), key=lambda x: int(x) if str(x).isdigit() else x):
            uv = pause_match[k]
            lines.append(
                f"    ref#{k} → {f'{uv:.2f}s' if uv is not None else '미매칭'}"
            )

    process = summary.get("scoring_process") or []
    if process:
        lines.append("  채점 과정:")
        for step in process:
            lines.append(f"    · {step}")

    segments = motion.get("segments") or []
    scored_segs = [s for s in segments if not s.get("skipped")]
    if scored_segs and bd.get("scoring_mode") == "boundary":
        lines.append("  구간별:")
        for s in scored_segs[:10]:
            rw = s.get("ref_window_sec") or []
            intr = s.get("interior_user_boundaries_sec") or []
            lines.append(
                f"    #{s.get('index')} ref {rw[0]}~{rw[1]}s  "
                f"양끝[{'O' if s.get('start_matched') else 'X'}"
                f"{'O' if s.get('end_matched') else 'X'}]  "
                f"사이구분 {len(intr)}개 {_fmt_times(intr, limit=5)}  "
                f"→ {s.get('segment_points_earned')}/{s.get('segment_points_max')}pt "
                f"({s.get('segment_score')}점)"
            )
        if len(scored_segs) > 10:
            lines.append(f"    ... 외 {len(scored_segs) - 10}구간")

    cap = summary.get("interior_scoring_cap", bd.get("interior_scoring_cap"))
    if cap is not None:
        lines.append(
            f"  사이 구분 상한: {summary.get('interior_counted_count', 0)}/{cap}개 반영 "
            f"(초과 {summary.get('interior_ignored_count', 0)}개 무시, "
            f"{bd.get('points_per_interior', 2)}점/개)"
        )
    if bd.get("perfect_score") is not None:
        lines.append(
            f"  획득=최대(100점): {'예' if bd.get('perfect_score') else '아니오'}  "
            f"({bd.get('points_earned')}/{bd.get('points_max')})"
        )


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
    motion = payload.get("motion") or creativity.get("motion")
    bd_c = creativity.get("breakdown") or {}
    score_src = bd_c.get("score_source") or inputs.get("analysis_mode", "motion")
    lines.append(f"  창의성 점수: {creativity.get('score', 0):.2f} / 100")
    lines.append(f"  채점 기준:   동작 측면 ({score_src})")
    _append_motion_scoring_detail(lines, motion)
    if accuracy:
        lines.append(f"  정확도 점수: {accuracy.get('score', 0):.2f} / 100 (참고)")
    lines.append("")
    lines.append("- 입력")
    lines.append(f"  사용자:     {_fmt_path(inputs.get('user', ''))}")
    lines.append(f"  레퍼런스:   {_fmt_path(inputs.get('reference', ''))}")
    lines.append(f"  미디어:     {inputs.get('media_type', '-')}")
    if inputs.get("media_type") == "video" or inputs.get("segment_mode"):
        lines.append(
            f"  동작 단위: motion_idle, "
            f"n={inputs.get('num_motion_units', 3)}, "
            f"idle>={inputs.get('idle_min_frames', 3)}fr"
        )
        seg_det = payload.get("segment_detection") or {}
        lines.append(
            f"  선택 구간: {seg_det.get('segment_count', '-')}개  "
            f"방법: {seg_det.get('method', '-')}"
        )
        if seg_det.get("motion_velocity_threshold") is not None:
            lines.append(f"  정지 임계: {seg_det.get('motion_velocity_threshold')}")
        timing = payload.get("timing") or breakdown.get("timing") or {}
        aw = timing.get("analysis_window") or {}
        if aw:
            ref_w = aw.get("reference") or {}
            user_w = aw.get("user") or {}
            lines.append(
                f"  분석 구간: ref {ref_w.get('start_sec')}~{ref_w.get('end_sec')}s  "
                f"user {user_w.get('start_sec')}~{user_w.get('end_sec')}s"
            )
        scoring_units = timing.get("scoring_motion_units") or []
        if scoring_units:
            lines.append("  채점 동작 단위:")
            for u in scoring_units[:12]:
                if not u.get("used_in_final_score"):
                    continue
                rt = u.get("reference_time") or {}
                ut = u.get("user_time") or {}
                lines.append(
                    f"    #{u.get('index')}  {u.get('creativity_score')}점  "
                    f"ref {rt.get('start_sec')}~{rt.get('end_sec')}s  "
                    f"user {ut.get('start_sec')}~{ut.get('end_sec')}s"
                )
        high_m = timing.get("high_creativity_motions") or []
        if high_m:
            lines.append("  고창의성 동작:")
            for h in high_m[:8]:
                rt = h.get("reference_time") or {}
                ut = h.get("user_time") or {}
                lines.append(
                    f"    #{h.get('segment_index')}  {h.get('creativity_score')}점  "
                    f"ref {rt.get('start_sec')}~{rt.get('end_sec')}s  "
                    f"user {ut.get('start_sec')}~{ut.get('end_sec')}s"
                )
        bd_seg = breakdown.get("per_segment_scores") or []
        if bd_seg and not scoring_units:
            lines.append("  구간별 점수:")
            for s in bd_seg[:12]:
                fc = s.get("frame_count", "")
                fc_txt = f", {fc}fr" if fc else ""
                rt = s.get("reference_time") or {}
                ut = s.get("user_time") or {}
                t_txt = ""
                if rt and ut:
                    t_txt = (
                        f"  ref {rt.get('start_sec')}~{rt.get('end_sec')}s"
                        f" user {ut.get('start_sec')}~{ut.get('end_sec')}s"
                    )
                lines.append(
                    f"    #{s.get('index')}  {s.get('score')}점  "
                    f"({s.get('duration_sec')}s{fc_txt}){t_txt}"
                )
            if len(bd_seg) > 12:
                lines.append(f"    ... 외 {len(bd_seg) - 12}구간")
        if breakdown.get("weighted_mean_score") is not None:
            lines.append(
                f"  가중평균: {breakdown.get('weighted_mean_score')}  "
                f"최저: {breakdown.get('min_segment_score')}"
            )
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
        if breakdown.get("llm_applied") or breakdown.get("formula_score") is not None:
            lines.append("")
            lines.append("- LLM 하이브리드 보정")
            lines.append(f"  수식 점수:     {breakdown.get('formula_score', '-')}")
            lines.append(f"  LLM 계수:      {breakdown.get('llm_adjustment', '-')}")
            lines.append(f"  최종 점수:     {breakdown.get('score_after_llm', creativity.get('score'))}")
            if breakdown.get("llm_rationale"):
                lines.append(f"  근거:          {breakdown['llm_rationale']}")
            if breakdown.get("llm_flags"):
                lines.append(f"  flags:         {', '.join(breakdown['llm_flags'])}")
            if breakdown.get("llm_error"):
                lines.append(f"  LLM 오류:      {breakdown['llm_error']} (계수 1.0 적용)")
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


def _print_split_screen_report(payload: dict, *, out_path: Path, render_path: str) -> None:
    creativity = payload.get("creativity") or {}
    score = creativity.get("score", 0)
    bd = creativity.get("breakdown") or {}
    split = payload.get("split_screen") or {}
    inputs = payload.get("inputs") or {}

    sep = "=" * 52
    lines = [
        sep,
        "  분할 화면(Split-screen) 창의성 비교",
        sep,
        "",
        f"  ★ 창의성 점수: {score:.2f} / 100",
        "",
    ]
    motion = payload.get("motion") or creativity.get("motion")
    _append_motion_scoring_detail(lines, motion)
    lines += [
        f"  영상:       {_fmt_path(inputs.get('user', ''))}",
        f"  분할 비율:  {split.get('split_ratio', inputs.get('split_ratio', '-'))}",
        f"  좌측 역할:  {split.get('left_role', '-')} → user 패널: {split.get('user_panel', '-')}",
        f"  정렬:       {inputs.get('alignment', '-')}",
        f"  채점 모드:  {inputs.get('analysis_mode', 'motion')}",
        f"  동작 구분:  {inputs.get('motion_segmentation', 'activation')}",
        f"  동작 채점:  {inputs.get('motion_scoring', 'boundary')}",
    ]
    if bd.get("mean_divergence") is not None:
        lines.append(f"  mean 이탈:  {bd.get('mean_divergence')}")
    if bd.get("dtw_mean_cost") is not None:
        lines.append(f"  DTW 비용:   {bd.get('dtw_mean_cost')}")
    timing = payload.get("timing") or bd.get("timing") or {}
    for u in (timing.get("scoring_motion_units") or [])[:6]:
        if not u.get("used_in_final_score"):
            continue
        rt, ut = u.get("reference_time") or {}, u.get("user_time") or {}
        lines.append(
            f"  채점 #{u.get('index')}: ref {rt.get('start_sec')}~{rt.get('end_sec')}s  "
            f"user {ut.get('start_sec')}~{ut.get('end_sec')}s  ({u.get('creativity_score')}점)"
        )
    for h in (timing.get("high_creativity_motions") or [])[:4]:
        rt, ut = h.get("reference_time") or {}, h.get("user_time") or {}
        lines.append(
            f"  고창의 #{h.get('segment_index')}: ref {rt.get('start_sec')}~{rt.get('end_sec')}s  "
            f"user {ut.get('start_sec')}~{ut.get('end_sec')}s  ({h.get('creativity_score')}점)"
        )
    lines.extend([
        "",
        f"  결과 영상:  {render_path}",
        f"  JSON:       {out_path}",
        sep,
    ])
    print("\n".join(lines))


def cmd_split_screen(args: argparse.Namespace) -> int:
    video = args.split_video or args.user
    if not video:
        print("--video 또는 --user 로 분할 화면 영상 경로를 지정하세요.", file=sys.stderr)
        return 1
    video_path = _require_file(video, "영상")

    out_path = Path(args.output) if args.output else default_output_path()
    render_out = Path(args.render_output) if args.render_output else (
        _OUTPUT_ROOT / f"split_creativity_{out_path.stem}.mp4"
    )

    try:
        payload = analyze_split_screen_video(
            video_path,
            split_ratio=args.split_ratio,
            left_role=args.left_role,
            music_align=args.music_align,
            baseline=args.baseline,
            with_accuracy=args.with_accuracy,
            with_llm_adjustment=args.with_llm,
            alignment=args.alignment,
            apply_mirror=args.apply_mirror,
            visibility_threshold=args.visibility_threshold,
            num_motion_units=args.num_motion_units,
            idle_min_frames=args.idle_min_frames,
            motion_velocity_threshold=args.motion_threshold,
            analysis_mode=args.analysis_mode,
            pause_tuning_level=args.pause_tuning_level,
            motion_segmentation=args.motion_segmentation,
            motion_scoring=args.motion_scoring,
            render_output=render_out,
            left_label=args.left_label,
            right_label=args.right_label,
            save_extractions=bool(args.save_dir),
        )
    except (ValueError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 1

    _save_json(payload, out_path)
    render_path = (payload.get("render") or {}).get("output_video", str(render_out))

    if args.json_stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_split_screen_report(payload, out_path=out_path, render_path=render_path)
        print(f"\n상세 JSON: {out_path}", file=sys.stderr)
        print(f"시각화 영상: {render_path}", file=sys.stderr)
    return 0


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
            user_offset_sec=args.user_offset,
            ref_offset_sec=args.ref_offset,
            auto_detect_start=args.auto_detect_start,
            music_align=args.music_align,
            baseline=args.baseline,
            with_accuracy=args.with_accuracy,
            with_llm_adjustment=args.with_llm,
            alignment=args.alignment,
            apply_mirror=args.apply_mirror,
            visibility_threshold=args.visibility_threshold,
            save_extractions=True,
            save_dir=save_dir,
            num_motion_units=args.num_motion_units,
            idle_min_frames=args.idle_min_frames,
            motion_velocity_threshold=args.motion_threshold,
            min_blend_weight=args.min_blend_weight,
            analysis_mode=args.analysis_mode,
            pause_tuning_level=args.pause_tuning_level,
            motion_segmentation=args.motion_segmentation,
            motion_scoring=args.motion_scoring,
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
    parser.add_argument("--user", help="사용자 영상 또는 이미지 (또는 --split-screen 시 단일 영상)")
    parser.add_argument("--reference", help="레퍼런스 영상 또는 이미지")
    parser.add_argument(
        "--split-screen",
        action="store_true",
        help="한 영상 좌/우 분할 비교 + 스켈레톤 결과 영상 생성",
    )
    parser.add_argument(
        "--video",
        dest="split_video",
        default=None,
        help="분할 화면 단일 영상 (--split-screen)",
    )
    parser.add_argument(
        "--render-output",
        default=None,
        help="스켈레톤·점수 오버레이 결과 mp4 경로",
    )
    parser.add_argument("--left-label", default="Reference", help="좌측(레퍼런스) 라벨 (ASCII 권장)")
    parser.add_argument("--right-label", default="Compare", help="우측(비교) 라벨 (ASCII 권장)")
    parser.add_argument(
        "--split-ratio",
        type=float,
        default=0.5,
        help="좌측 패널 너비 비율 0.35~0.65 (기본 0.5)",
    )
    parser.add_argument(
        "--left-role",
        choices=("user", "reference"),
        default="user",
        help="좌측을 user로 둘지 reference로 둘지 (기본 user)",
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
        help="동일 BGM 전제 크로마 구간 [시작,끝] 정렬 (기본 on)",
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
        "--with-llm",
        action="store_true",
        help="수식 점수 × LLM 보정(0.8~1.2). Ollama localhost:11434 필요",
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
    parser.add_argument(
        "--analysis-mode",
        choices=("legacy", "rhythm", "motion", "both"),
        default="motion",
        help="채점: motion=동작(기본), both=motion과 동일, rhythm=박자만, legacy=구 motion_idle",
    )
    parser.add_argument(
        "--pause-tuning-level",
        type=int,
        default=0,
        choices=range(6),
        metavar="0-5",
        help="pause 분할 시 튜닝 단계 (motion-segmentation=pause 일 때만)",
    )
    parser.add_argument(
        "--motion-segmentation",
        choices=("activation", "pause"),
        default="activation",
        help="동작 구간 경계: activation=가동관절 전환(기본), pause=멈춤",
    )
    parser.add_argument(
        "--motion-scoring",
        choices=("boundary", "pose"),
        default="boundary",
        help="동작 채점: boundary=구간·세분화 매칭(기본), pose=포즈 이탈",
    )
    parser.add_argument(
        "--num-motion-units",
        type=int,
        default=3,
        metavar="N",
        help="비교할 동작 단위 개수 (기본 3)",
    )
    parser.add_argument(
        "--idle-min-frames",
        type=int,
        default=3,
        metavar="N",
        help="이 프레임 이상 거의 정지 → 동작 시작/끝 경계 (기본 3)",
    )
    parser.add_argument(
        "--motion-threshold",
        type=float,
        default=None,
        help="정지 판정 속도 상한 (미지정 시 자동)",
    )
    parser.add_argument(
        "--min-blend-weight",
        type=float,
        default=0.15,
        help="최저 구간 점수 블렌드 비율 0~0.5 (기본 0.15)",
    )

    args = parser.parse_args(argv)
    if args.split_screen or args.split_video:
        return cmd_split_screen(args)
    if not args.user or not args.reference:
        print("--user 와 --reference 가 필요합니다 (또는 --split-screen).", file=sys.stderr)
        return 1
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
