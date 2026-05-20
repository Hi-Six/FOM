import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from services.analyze_service import run_analyze, run_extraction_and_save, save_upload_to_temp
from services.storage_paths import load_extraction_json

router = APIRouter(prefix="/video", tags=["video"])


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
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(file)
        result = run_extraction_and_save(tmp_path)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/analyze", summary="사용자 영상 업로드 → 추출 → 리듬 채점")
async def analyze_video(user_video: UploadFile = File(...)):
    tmp_path = None
    try:
        tmp_path, _ = await save_upload_to_temp(user_video)
        result = run_analyze(tmp_path)
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
