"""Isolation 추출(YOLO + MediaPipe) 디바이스 해석 — 기본 GPU(CUDA) 우선."""

from __future__ import annotations

from typing import Any, Optional, Tuple


def _torch_cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def resolve_yolo_device(device: Optional[str] = None) -> Any:
    """
    Ultralytics YOLO track device.

    - None / auto / gpu / cuda → CUDA 있으면 0, 없으면 cpu
    - 0, cuda:0, cpu 등은 그대로 전달
    """
    if device is None or str(device).strip().lower() in ("auto", "default", ""):
        return 0 if _torch_cuda_available() else "cpu"
    d = str(device).strip().lower()
    if d in ("gpu", "cuda"):
        return 0 if _torch_cuda_available() else "cpu"
    if d.isdigit():
        return int(d)
    return device


def resolve_mediapipe_delegate(device: Optional[str] = None) -> str:
    """
    MediaPipe PoseLandmarker delegate 모드.

    - auto / gpu / cuda → gpu (생성 실패 시 mediapipe_pose_tasks 가 cpu 로 fallback)
    - cpu → cpu 만
    """
    if device is None or str(device).strip().lower() in ("auto", "default", ""):
        return "gpu" if _torch_cuda_available() else "cpu"
    d = str(device).strip().lower()
    if d in ("gpu", "cuda", "0") or d.isdigit():
        return "gpu"
    if d == "cpu":
        return "cpu"
    return "gpu" if _torch_cuda_available() else "cpu"


def resolve_extraction_devices(
    device: Optional[str] = None,
) -> Tuple[Any, str, str]:
    """
    (yolo_device, mediapipe_delegate, label) — 로그·JSON 메타용.
    label 예: cuda:0+mediapipe_gpu, cpu
    """
    yolo = resolve_yolo_device(device)
    mp_del = resolve_mediapipe_delegate(device)
    if yolo == "cpu" and mp_del == "cpu":
        label = "cpu"
    elif mp_del == "gpu":
        label = f"{yolo}+mediapipe_gpu"
    else:
        label = f"{yolo}+mediapipe_{mp_del}"
    return yolo, mp_del, label
