import os
import time
from typing import Annotated, Dict, Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from metrics.rhythm.services.scoring.rhythm_scorer import VALID_GENRES
from metrics.rhythm.services.analyze_service import (
    run_analyze,
    run_analyze_full,
    run_analyze_with_beats,
    run_analyze_with_reference,
    run_compare_visualize,
    run_extraction_and_save,
    run_visualize,
    run_visualize_full,
    save_upload_to_temp,
)
from metrics.rhythm.services.storage_paths import VIDEO_DATA_DIR, load_extraction_json

router = APIRouter(prefix="/rhythm", tags=["rhythm"])


def _inject_upload_timing(result: Dict[str, Any], upload_sec: float, t0: float) -> Dict[str, Any]:
    timing = result.setdefault("timing_sec", {})
    timing["upload_sec"] = round(upload_sec, 3)
    timing["request_total_sec"] = round(time.perf_counter() - t0, 3)
    return result


# ── 파일 다운로드 ─────────────────────────────────────────────────

@router.get("/video-data/{filename}", summary="생성된 시각화 영상 다운로드")
def download_video(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = VIDEO_DATA_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {filename}")
    return FileResponse(str(path), media_type="video/mp4", filename=filename)


# ── 시각화 ───────────────────────────────────────────────────────

@router.post(
    "/compare-visualize",
    summary="원본 + 사용자 영상 나란히 비교 — 싱크 불일치 구간 검은 화면",
)
async def compare_visualize(
    user_video: UploadFile = File(...),
    reference_video: UploadFile = File(...),
    genre: str = Form(default="girl_idol"),
):
    """
    원본(왼쪽)과 사용자(오른쪽)를 나란히 재생하며 싱크를 시각화.

    - 싱크 양호 구간: 양쪽 정상 재생
    - 싱크 불일치 구간: 양쪽 모두 검은 화면 페이드
    - 하단 인디케이터: 초록(양호) → 빨강(불량) 타임라인
    - `genre`: `girl_idol` / `boy_idol` / `default`
    """
    _validate_genre(genre)
    t0 = time.perf_counter()
    user_tmp = ref_tmp = None
    try:
        user_tmp, _ = await save_upload_to_temp(user_video)
        ref_tmp, _ = await save_upload_to_temp(reference_video)
        t_up = time.perf_counter()
        result = run_compare_visualize(user_tmp, ref_tmp, genre=genre)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"비교 시각화 중 오류: {e}")
    finally:
        for p in (user_tmp, ref_tmp):
            if p and os.path.exists(p):
                os.remove(p)


@router.post("/visualize", summary="영상 업로드 → 리듬 시각화 영상 생성 (비트 옵션)")
async def visualize_video(
    user_video: UploadFile = File(...),
    with_beats: bool = False,
    genre: str = Form(default="girl_idol"),
):
    """
    - `genre`: `girl_idol` (기본) / `boy_idol` / `default`
    - `with_beats=false` (기본): 키포인트·속도·피크만 시각화
    - `with_beats=true`: 음악 비트까지 추출하여 타임라인에 표시
    """
    _validate_genre(genre)
    t0 = time.perf_counter()
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(user_video)
        t_up = time.perf_counter()
        result = run_visualize(tmp_path, beat=with_beats, genre=genre)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시각화 중 오류: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post(
    "/visualize-full",
    summary="사용자 영상 + 레퍼런스 영상 → 통합 채점 + 시각화 영상 생성",
)
async def visualize_full(
    user_video: UploadFile = File(...),
    reference_video: UploadFile = File(...),
    genre: str = Form(default="girl_idol"),
):
    """
    - `genre`: `girl_idol` (기본) / `boy_idol` / `default`
    - 레퍼런스에서 동작·비트를 추출하고 사용자 영상에 비교 결과를 오버레이.
    """
    _validate_genre(genre)
    t0 = time.perf_counter()
    user_tmp = ref_tmp = None
    try:
        user_tmp, _ = await save_upload_to_temp(user_video)
        ref_tmp, _ = await save_upload_to_temp(reference_video)
        t_up = time.perf_counter()
        result = run_visualize_full(user_tmp, ref_tmp, genre=genre)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시각화 중 오류: {e}")
    finally:
        for p in (user_tmp, ref_tmp):
            if p and os.path.exists(p):
                os.remove(p)


@router.get("/json/{filename}", summary="저장된 추출 JSON 다운로드")
def get_extraction_json(filename: str):
    try:
        data = load_extraction_json(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return JSONResponse(content=data)


@router.post("/extract", summary="영상에서 리듬 랜드마크 추출 + JSON 저장")
async def extract_video(file: UploadFile = File(...)):
    t0 = time.perf_counter()
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(file)
        t_up = time.perf_counter()
        result = run_extraction_and_save(tmp_path)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post(
    "/analyze-full",
    summary="사용자 영상 + 레퍼런스 영상 → 동작 유사도(DTW) + 비트 타이밍 통합 채점",
)
async def analyze_full(
    user_video: UploadFile = File(...),
    reference_video: UploadFile = File(...),
    genre: str = Form(default="girl_idol"),
):
    """
    - `genre`: `girl_idol` (기본) / `boy_idol` / `default`
    - DTW  50%: 레퍼런스 동작 패턴과의 유사도
    - Beat 50%: 레퍼런스 영상 음악 비트 적중률
    """
    _validate_genre(genre)
    t0 = time.perf_counter()
    user_tmp = ref_tmp = None
    try:
        user_tmp, _ = await save_upload_to_temp(user_video)
        ref_tmp, _ = await save_upload_to_temp(reference_video)
        t_up = time.perf_counter()
        result = run_analyze_full(user_tmp, ref_tmp, genre=genre)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {e}")
    finally:
        for p in (user_tmp, ref_tmp):
            if p and os.path.exists(p):
                os.remove(p)


@router.post("/analyze-beats", summary="영상 업로드 → 포즈 추출 + 음악 비트 추출 → 비트 대비 동작 채점")
async def analyze_beats(
    user_video: UploadFile = File(...),
    genre: str = Form(default="girl_idol"),
):
    """- `genre`: `girl_idol` (기본) / `boy_idol` / `default`"""
    _validate_genre(genre)
    t0 = time.perf_counter()
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(user_video)
        t_up = time.perf_counter()
        result = run_analyze_with_beats(tmp_path, genre=genre)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post(
    "/analyze",
    summary="사용자 영상 업로드 → 추출 → 리듬 채점 (reference_video 첨부 시 DTW 비교)",
)
async def analyze_video(
    user_video: UploadFile = File(...),
    reference_video: Annotated[Optional[UploadFile], File()] = None,
    genre: str = Form(default="girl_idol"),
):
    """
    - `genre`: `girl_idol` (기본) / `boy_idol` / `default`
    - `reference_video` 없음: 자기일관성(리듬 규칙성) 채점
    - `reference_video` 있음: 레퍼런스와 DTW 비교 + 자기일관성 혼합 채점
    """
    _validate_genre(genre)
    t0 = time.perf_counter()
    user_tmp = ref_tmp = None
    try:
        user_tmp, _ = await save_upload_to_temp(user_video)
        has_reference = reference_video is not None and bool(reference_video.filename)
        if has_reference:
            ref_tmp, _ = await save_upload_to_temp(reference_video)
        t_up = time.perf_counter()
        if has_reference:
            result = run_analyze_with_reference(user_tmp, ref_tmp, genre=genre)
        else:
            result = run_analyze(user_tmp, genre=genre)
        _inject_upload_timing(result, t_up - t0, t0)
        return JSONResponse(content=result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {e}")
    finally:
        for p in (user_tmp, ref_tmp):
            if p and os.path.exists(p):
                os.remove(p)


def _validate_genre(genre: str) -> None:
    if genre not in VALID_GENRES:
        raise HTTPException(
            status_code=422,
            detail=f"지원하지 않는 장르입니다. 허용값: {sorted(VALID_GENRES)}",
        )
