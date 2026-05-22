"""업로드 영상 → isolation 추출·정렬·채점 (HTTP·CLI 공용)."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from metrics.isolation.config import DATA_ARTIFACTS
from metrics.isolation.pipeline.extract import extract_and_save
from metrics.isolation.score import score_from_paths

REF_JSON = DATA_ARTIFACTS / "ref.json"
MAX_FRAME_DIFFS_IN_RESPONSE = 20


def ensure_reference_ready() -> Path:
    if not REF_JSON.is_file():
        raise FileNotFoundError(
            "기준 추출 JSON(ref.json)이 없습니다. "
            "서버에서 한 번 실행: python -m metrics.isolation.cli extract"
        )
    return REF_JSON


def analyze_user_video(
    user_video_path: str | Path,
    *,
    user_offset_sec: float = 0.0,
    ref_offset_sec: float = 0.0,
    auto_detect_start: bool = False,
    keep_user_json: bool = False,
) -> Dict[str, Any]:
    """
    사용자 mp4 → isolation 점수 dict.

    ARCHITECTURE: 통합 /video/analyze 와 분리. isolation 전용.
    """
    ref_json = ensure_reference_ready()
    video_path = Path(user_video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"영상 없음: {video_path}")

    work = Path(tempfile.mkdtemp(prefix="iso_upload_"))
    user_json = work / f"user_{uuid.uuid4().hex[:8]}.json"
    persisted_json: Optional[Path] = None
    try:
        extract_and_save(
            video_path,
            user_json,
            tracks_json_path=None,
            reuse_yolo=True,
            progress_every=0,
        )
        if keep_user_json:
            DATA_ARTIFACTS.mkdir(parents=True, exist_ok=True)
            persisted_json = DATA_ARTIFACTS / user_json.name
            shutil.copy2(user_json, persisted_json)
        raw = score_from_paths(
            str(user_json),
            str(ref_json),
            user_offset_sec=user_offset_sec,
            ref_offset_sec=ref_offset_sec,
            auto_detect_start=auto_detect_start,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    frame_diffs = raw.get("frame_diffs") or []
    if len(frame_diffs) > MAX_FRAME_DIFFS_IN_RESPONSE:
        worst = sorted(frame_diffs, key=lambda x: x.get("score", 100))[
            :MAX_FRAME_DIFFS_IN_RESPONSE
        ]
        raw["frame_diffs"] = worst
        raw.setdefault("breakdown", {})["frame_diffs_truncated"] = True

    out: Dict[str, Any] = {
        "metric": "isolation",
        "score": raw.get("score", 0.0),
        "breakdown": raw.get("breakdown", {}),
        "alignment": raw.get("alignment"),
        "frame_diffs": raw.get("frame_diffs", []),
    }
    if persisted_json is not None:
        out["user_json_path"] = str(persisted_json)
    return out
