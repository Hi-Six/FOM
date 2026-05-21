"""
기준·사용자 영상을 data/raw/ 에 저장.

사용 (backend1 루트 또는 isolation 폴더에서):
  python -m metrics.isolation.scripts.download_videos
  python -m metrics.isolation.scripts.download_videos --user-url "https://..."
  python metrics/isolation/scripts/download_videos.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# metrics.isolation.config import (스크립트 직접 실행 대비)
_ISOLATION_ROOT = Path(__file__).resolve().parents[1]
if str(_ISOLATION_ROOT.parents[1]) not in sys.path:
    sys.path.insert(0, str(_ISOLATION_ROOT.parents[1]))

from metrics.isolation.config import DATA_RAW, REF_VIDEO_NAME, REF_VIDEO_URL  # noqa: E402


def _ensure_yt_dlp() -> None:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("yt-dlp가 필요합니다: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)


def download(url: str, out_path: Path) -> Path:
    """URL → mp4 (단일 파일)."""
    _ensure_yt_dlp()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_template = str(out_path.with_suffix("")) + ".%(ext)s"

    # 단일 파일(mp4) 우선 — ffmpeg 병합 없이 동작
    opts = {
        "format": "best[ext=mp4][height<=1080]/best[ext=mp4]/best",
        "outtmpl": out_template,
        "quiet": False,
        "no_warnings": False,
    }
    import yt_dlp

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    # yt-dlp가 확장자를 붙일 수 있음
    if out_path.is_file():
        return out_path
    candidates = list(out_path.parent.glob(out_path.stem + ".*"))
    mp4s = [p for p in candidates if p.suffix.lower() in {".mp4", ".webm", ".mkv"}]
    if not mp4s:
        raise FileNotFoundError(f"다운로드 실패: {url} → {out_path}")
    found = mp4s[0]
    if found != out_path and found.suffix.lower() == ".mp4":
        found.rename(out_path)
    elif found != out_path:
        # webm 등 → mp4 이름으로 복사 대신 그대로 안내
        return found
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="isolation 검증용 영상 다운로드")
    parser.add_argument(
        "--ref-url",
        default=REF_VIDEO_URL,
        help="기준(레퍼런스) YouTube URL",
    )
    parser.add_argument(
        "--user-url",
        default=None,
        help="사용자 비교용 URL (없으면 ref만)",
    )
    parser.add_argument(
        "--user-file",
        type=Path,
        default=None,
        help="이미 있는 로컬 mp4를 data/raw/user.mp4 로 복사",
    )
    args = parser.parse_args()

    ref_path = DATA_RAW / REF_VIDEO_NAME
    print(f"[ref] {args.ref_url} → {ref_path}")
    download(args.ref_url, ref_path)
    print(f"  저장: {ref_path.resolve()}")

    if args.user_url:
        user_path = DATA_RAW / "user.mp4"
        print(f"[user] {args.user_url} → {user_path}")
        download(args.user_url, user_path)
        print(f"  저장: {user_path.resolve()}")

    if args.user_file:
        import shutil

        user_path = DATA_RAW / "user.mp4"
        if not args.user_file.is_file():
            print(f"파일 없음: {args.user_file}", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(args.user_file, user_path)
        print(f"[user] 복사: {user_path.resolve()}")


if __name__ == "__main__":
    main()
