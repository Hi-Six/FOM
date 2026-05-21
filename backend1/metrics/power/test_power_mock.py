import json
import sys
import os

# backend1 폴더를 Python 경로에 추가 (어디서 실행해도 동작)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from metrics.power import score_power


def make_frame(i, speed=0.05):
    joints = [
        "left_wrist", "right_wrist",
        "left_elbow", "right_elbow",
        "left_ankle", "right_ankle",
        "left_knee", "right_knee",
        "left_hip", "right_hip",
        "nose", "left_shoulder", "right_shoulder",
        "left_foot_index", "right_foot_index",
    ]
    pos = i * speed
    lms = {j: {"x": pos, "y": pos, "z": 0.0} for j in joints}
    return {"frame_index": i, "normalized_landmarks": lms}


# 느림 / 보통 / 빠름 3가지 케이스 테스트
for speed, label in [(0.01, "느림"), (0.05, "보통"), (0.10, "빠름")]:
    mock_data = {
        "fps": 30.0,
        "total_frames": 60,
        "frames": [make_frame(i, speed) for i in range(60)],
    }

    result = score_power(mock_data)

    # 콘솔 출력
    print(f"\n[{label}] speed={speed}")
    print(f"  파워 점수         : {result['score']}")
    print(f"  composite_velocity: {result['breakdown']['composite_velocity']}")
    print(f"  final_composite   : {result['breakdown']['final_composite']}")

    # JSON 파일 저장
    filename = f"metrics/power/power_result_{label}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  → {filename} 저장 완료")
