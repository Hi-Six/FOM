"""두 추출 시퀀스의 프레임 정렬."""

from typing import Any, Dict, List


def align_by_time(
    user_frames: List[Dict[str, Any]],
    ref_frames: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    사용자 각 프레임의 time_sec에 가장 가까운 레퍼런스 프레임을 매칭.
    반환: aligned_pairs (user_frame, ref_frame, user, ref 포함)
    """
    if not user_frames or not ref_frames:
        return []

    pairs: List[Dict[str, Any]] = []
    for uf in user_frames:
        u_t = float(uf.get("time_sec", 0.0))
        best_rf = min(
            ref_frames,
            key=lambda rf: abs(float(rf.get("time_sec", 0.0)) - u_t),
        )
        pairs.append({
            "user_frame": int(uf["frame_index"]),
            "ref_frame": int(best_rf["frame_index"]),
            "user": uf,
            "ref": best_rf,
        })
    return pairs
