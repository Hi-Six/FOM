"""

동작 측면 — 구간 경계 매칭·user 중간 구분(세분화) 기반 창의성.



- ref 구분점 매칭: 1점/개

- 양끝 매칭 구간 내 user 사이 구분: 2점/개 (구분점의 2배)

- 사이 구분 채점 상한: ref 구간 수 × 20% (초과분은 무시)

- 최종 점수 = 100 × 획득 / 최대 (만점 직통 없음, 동일 공식)

"""



from __future__ import annotations



import math

from typing import Any



_POINTS_PER_BOUNDARY = 1.0

_POINTS_PER_INTERIOR = 2.0 * _POINTS_PER_BOUNDARY

_INTERIOR_RATIO_CAP = 0.2





def _boundary_times(

    window_start: float,

    window_end: float,

    instants: list[float],

    segments: list[dict[str, Any]],

) -> list[float]:

    times: set[float] = {round(window_start, 4), round(window_end, 4)}

    for t in instants:

        times.add(round(float(t), 4))

    for seg in segments:

        times.add(round(float(seg["start_sec"]), 4))

        times.add(round(float(seg["end_sec"]), 4))

    return sorted(times)





def _near_boundary(boundaries: list[float], t: float, eps: float) -> bool:

    return any(abs(float(b) - float(t)) <= eps for b in boundaries)





def _nearest_user_boundary(

    user_boundaries: list[float], t: float, eps: float

) -> tuple[bool, float | None]:

    best_u: float | None = None

    best_d = eps + 1.0

    for u in user_boundaries:

        d = abs(float(u) - float(t))

        if d < best_d:

            best_d = d

            best_u = float(u)

    if best_u is not None and best_d <= eps:

        return True, round(best_u, 4)

    return False, None





def _nearest_ref_boundary(

    ref_boundaries: list[float],

    user_t: float,

    eps: float,

    time_delta_sec: float,

) -> tuple[bool, float | None]:

    best_r: float | None = None

    best_d = eps + 1.0

    for r in ref_boundaries:

        d = abs(float(r) + float(time_delta_sec) - float(user_t))

        if d < best_d:

            best_d = d

            best_r = float(r)

    if best_r is not None and best_d <= eps:

        return True, round(best_r, 4)

    return False, None





def _interior_user_boundaries(

    user_boundaries: list[float],

    r0: float,

    r1: float,

    eps: float,

    time_delta_sec: float,

    *,

    start_matched: bool,

    end_matched: bool,

) -> list[float]:

    """ref 구간 (r0,r1) 양끝 매칭 시, user 타임라인에서 그 사이 구분점만."""

    if not start_matched or not end_matched:

        return []

    lo = float(r0) + float(time_delta_sec) + eps

    hi = float(r1) + float(time_delta_sec) - eps

    if hi <= lo:

        return []

    inner: list[float] = []

    for u in user_boundaries:

        uf = float(u)

        if lo < uf < hi:

            inner.append(round(uf, 4))

    return sorted(inner)





def _interior_scoring_cap(segment_count: int) -> int:

    if segment_count <= 0:

        return 0

    return max(0, round(_INTERIOR_RATIO_CAP * segment_count))





def score_motion_boundary_creativity(

    ref_segments: list[dict[str, Any]],

    ref_instants: list[float],

    user_instants: list[float],

    *,

    ref_window_start: float,

    ref_window_end: float,

    user_window_start: float,

    user_window_end: float,

    epsilon_sec: float,

    time_delta_sec: float = 0.0,

    user_segment_count: int | None = None,

) -> dict[str, Any]:

    """

    ref 구간·구분점 vs user 구분점 매칭으로 동작 창의성 점수 산출.

    time_delta_sec: user_time ≈ ref_time + delta (분할 화면 동일 타임라인이면 0).

    """

    ref_bounds = _boundary_times(

        ref_window_start, ref_window_end, ref_instants, ref_segments

    )

    user_bounds = _boundary_times(

        user_window_start, user_window_end, user_instants, []

    )



    def _user_time_for_ref(ref_t: float) -> float:

        return float(ref_t) + float(time_delta_sec)



    ref_instant_matched: list[bool] = []

    for rt in ref_instants:

        ref_instant_matched.append(

            _near_boundary(user_bounds, _user_time_for_ref(rt), epsilon_sec)

        )

    all_ref_instants_matched = (

        all(ref_instant_matched) if ref_instants else True

    )



    segment_rows: list[dict[str, Any]] = []

    all_interior_candidates: list[float] = []



    for seg in ref_segments:

        r0 = float(seg["start_sec"])

        r1 = float(seg["end_sec"])

        u0_ref = _user_time_for_ref(r0)

        u1_ref = _user_time_for_ref(r1)

        start_ok = _near_boundary(user_bounds, u0_ref, epsilon_sec)

        end_ok = _near_boundary(user_bounds, u1_ref, epsilon_sec)

        interiors = _interior_user_boundaries(

            user_bounds,

            r0,

            r1,

            epsilon_sec,

            time_delta_sec,

            start_matched=start_ok,

            end_matched=end_ok,

        )

        all_interior_candidates.extend(interiors)



        segment_rows.append(

            {

                "index": int(seg.get("index", 0)),

                "ref_window_sec": [round(r0, 4), round(r1, 4)],

                "user_window_sec": [

                    round(_user_time_for_ref(r0), 4),

                    round(_user_time_for_ref(r1), 4),

                ],

                "start_matched": start_ok,

                "end_matched": end_ok,

                "interior_user_boundaries_sec": interiors,

                "interior_count": len(interiors),

            }

        )



    n_seg = len(ref_segments)

    interior_cap = _interior_scoring_cap(n_seg)

    all_interior_sorted = sorted(set(all_interior_candidates))

    counted_interiors = all_interior_sorted[:interior_cap]

    ignored_interiors = all_interior_sorted[interior_cap:]

    counted_interior_set = set(counted_interiors)

    segments_with_interior = sum(

        1

        for row in segment_rows

        if row["start_matched"]

        and row["end_matched"]

        and row["interior_count"] > 0

    )

    interior_ratio = segments_with_interior / n_seg if n_seg else 0.0



    ref_boundary_points: list[dict[str, Any]] = []

    matched_ref_boundaries_sec: list[float] = []

    boundary_earned = 0.0

    for t in ref_bounds:

        ut = _user_time_for_ref(t)

        ok, user_t = _nearest_user_boundary(user_bounds, ut, epsilon_sec)

        ref_boundary_points.append(

            {

                "ref_sec": round(float(t), 4),

                "user_sec": user_t,

                "matched": ok,

                "delta_sec": (

                    round(abs(ut - float(user_t)), 4) if user_t is not None else None

                ),

            }

        )

        if ok:

            matched_ref_boundaries_sec.append(round(float(t), 4))

            boundary_earned += _POINTS_PER_BOUNDARY



    user_boundary_points: list[dict[str, Any]] = []

    matched_user_boundaries_sec: list[float] = []

    for u in user_bounds:

        ok, ref_t = _nearest_ref_boundary(

            ref_bounds, float(u), epsilon_sec, time_delta_sec

        )

        user_boundary_points.append(

            {

                "user_sec": round(float(u), 4),

                "ref_sec": ref_t,

                "matched": ok,

                "delta_sec": (

                    round(abs(float(u) - (float(ref_t) + float(time_delta_sec))), 4)

                    if ref_t is not None

                    else None

                ),

            }

        )

        if ok:

            matched_user_boundaries_sec.append(round(float(u), 4))



    boundary_matching = ref_boundary_points

    ref_boundary_match_count = sum(1 for m in ref_boundary_points if m["matched"])

    user_boundary_match_count = sum(1 for m in user_boundary_points if m["matched"])

    all_ref_boundaries_matched = ref_boundary_match_count == len(ref_bounds)



    interior_earned = len(counted_interiors) * _POINTS_PER_INTERIOR

    earned = boundary_earned + interior_earned

    max_points = (

        len(ref_bounds) * _POINTS_PER_BOUNDARY

        + interior_cap * _POINTS_PER_INTERIOR

    )



    for row in segment_rows:

        interiors = row.get("interior_user_boundaries_sec") or []

        counted = [u for u in interiors if u in counted_interior_set]

        ignored = [u for u in interiors if u not in counted_interior_set]

        start_ok = bool(row["start_matched"])

        end_ok = bool(row["end_matched"])

        seg_earned = (

            (start_ok + end_ok) * _POINTS_PER_BOUNDARY

            + len(counted) * _POINTS_PER_INTERIOR

        )

        seg_max = (

            2 * _POINTS_PER_BOUNDARY + len(interiors) * _POINTS_PER_INTERIOR

        )

        row["interior_counted_sec"] = counted

        row["interior_ignored_sec"] = ignored

        row["segment_points_earned"] = round(seg_earned, 4)

        row["segment_points_max"] = round(seg_max, 4)

        row["segment_score"] = round(

            100.0 * seg_earned / seg_max if seg_max > 0 else 0.0, 2

        )



    final_score = round(

        min(100.0, 100.0 * earned / max_points if max_points > 0 else 0.0),

        2,

    )

    perfect = max_points > 0 and math.isclose(earned, max_points, rel_tol=0, abs_tol=1e-6)

    score_reason = "proportional_boundary_points"



    if user_segment_count is None:

        user_segment_count = max(1, len(user_instants) + 1)



    scoring_process: list[str] = [

        f"1) ref 동작 구간 {n_seg}개, user 동작 구간(추정) {user_segment_count}개, "

        f"경계 허용오차 ε={epsilon_sec:.3f}s, 시간보정 Δt={time_delta_sec:.3f}s",

        f"2) ref 구분점 {len(ref_bounds)}개 중 {ref_boundary_match_count}개 매칭 "

        f"({_POINTS_PER_BOUNDARY}점/개), "

        f"user 구분점 {len(user_bounds)}개 중 {user_boundary_match_count}개 매칭",

        f"3) 사이 구분 채점: {len(counted_interiors)}/{interior_cap}개 반영 "

        f"({_POINTS_PER_INTERIOR}점/개, 상한=구간수×{_INTERIOR_RATIO_CAP:.0%}), "

        f"초과 {len(ignored_interiors)}개 무시",

        f"4) 양끝 매칭+사이 구분 있는 구간 {segments_with_interior}개 "

        f"(참고 비율 {interior_ratio:.1%})",

        f"5) 획득 {earned:.2f} / 최대 {max_points:.2f} "

        f"(구분점 {boundary_earned:.1f} + 사이구분 {interior_earned:.1f})",

        f"6) 최종 점수 = 100×획득/최대 = {final_score:.2f}",

    ]



    return {

        "score": final_score,

        "scoring_summary": {

            "ref_segment_count": n_seg,

            "user_segment_count": user_segment_count,

            "ref_boundary_instant_count": len(ref_instants),

            "user_boundary_instant_count": len(user_instants),

            "ref_boundary_times_count": len(ref_bounds),

            "matched_boundary_count": ref_boundary_match_count,

            "matched_boundaries_sec": matched_ref_boundaries_sec,

            "matched_user_boundary_count": user_boundary_match_count,

            "matched_user_boundaries_sec": matched_user_boundaries_sec,

            "ref_boundary_times_sec": [round(t, 4) for t in ref_bounds],

            "user_boundary_times_sec": [round(t, 4) for t in user_bounds],

            "ref_boundary_points": ref_boundary_points,

            "user_boundary_points": user_boundary_points,

            "boundary_matching": boundary_matching,

            "interior_scoring_cap": interior_cap,

            "interior_boundary_count": len(all_interior_sorted),

            "interior_counted_count": len(counted_interiors),

            "interior_ignored_count": len(ignored_interiors),

            "interior_boundaries_sec": all_interior_sorted,

            "interior_counted_sec": counted_interiors,

            "interior_ignored_sec": ignored_interiors,

            "segments_with_interior": segments_with_interior,

            "scoring_process": scoring_process,

            "points_per_boundary": _POINTS_PER_BOUNDARY,

            "points_per_interior": _POINTS_PER_INTERIOR,

        },

        "breakdown": {

            "scoring_mode": "boundary",

            "score_reason": score_reason,

            "perfect_score": perfect,

            "all_ref_instants_matched": all_ref_instants_matched,

            "all_ref_boundaries_matched": all_ref_boundaries_matched,

            "ref_boundary_count": len(ref_bounds),

            "ref_boundary_matched_count": ref_boundary_match_count,

            "segment_count": n_seg,

            "segments_with_endpoint_match": sum(

                1 for r in segment_rows if r["start_matched"] and r["end_matched"]

            ),

            "segments_with_interior": segments_with_interior,

            "interior_segment_ratio": round(interior_ratio, 4),

            "interior_scoring_cap": interior_cap,

            "interior_ratio_cap": _INTERIOR_RATIO_CAP,

            "boundary_points_earned": round(boundary_earned, 4),

            "interior_points_earned": round(interior_earned, 4),

            "points_earned": round(earned, 4),

            "points_max": round(max_points, 4),

            "boundary_match_epsilon_sec": round(epsilon_sec, 4),

            "time_delta_sec": round(time_delta_sec, 4),

        },

        "ref_boundary_times_sec": ref_bounds,

        "user_boundary_times_sec": user_bounds,

        "segments": segment_rows,

    }


