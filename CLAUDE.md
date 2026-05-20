# Role
You are an expert Python Backend Developer and Computer Vision Engineer. Your task is to build the core Video Data Extraction Module for a Street Dance Analysis MVP.

# Project Context
- **Domain:** AI Street Dance Level Judgment Platform.
- **Architecture:** We have 6 separate scoring functions (ROM, Power, Isolation, Rhythm, Creativity, Accuracy) that will be developed by different team members. 
- **Goal:** To prevent server overload and ensure parallel development, you must build **ONE common extraction module**. This module will process an uploaded video once, extract the 3D landmarks, clean the data, normalize it, and return a standardized JSON array. This JSON will then be passed as an argument to the 6 scoring functions.

# Tech Stack & Constraints
- Python 3.9+
- `opencv-python` (cv2) for video processing.
- `mediapipe` (Pose solution) for 3D landmark extraction.
- `numpy`, `pandas`, `scipy` for mathematical operations, data smoothing, and interpolation.
- **Performance:** This is an MVP. Optimize for speed. If YOLO11 integration for bounding box tracking is too complex for a 1-week MVP, skip it and rely entirely on `mediapipe` with strict data smoothing.

# Pipeline Requirements (Crucial)
You must implement a class or function (e.g., `extract_dance_data(video_path)`) that strictly follows these 4 steps:

1. **Meta Data Extraction:**
   - Extract and store the `fps` (Frames Per Second) and `total_frames` using OpenCV. This is strictly required for the 'Rhythm' and 'Accuracy' scoring modules to align time.

2. **Raw Landmark Extraction:**
   - Run MediaPipe Pose on every frame.
   - Extract `x`, `y`, `z`, and `visibility` for all 33 landmarks.

3. **Data Smoothing & Interpolation (Mandatory):**
   - Dance videos have fast motions, causing MediaPipe to temporarily lose track or coordinates to jitter.
   - Use `pandas` `.interpolate(method='linear')` to fill missing frames (NaN values).
   - Apply a Moving Average filter (e.g., `rolling(window=3).mean()`) to remove high-frequency jitter. If this is skipped, the 'Power' (acceleration) scoring function will break.

4. **Normalization (Crucial for Accuracy Scoring):**
   - The 'Accuracy' module compares users with reference dancers of different body proportions. You must apply a 2-step normalization to eliminate body scale and position differences:
   - **Step A (Translation):** Calculate the 'Mid-Hip' (average of left_hip and right_hip). Shift all 33 coordinates so Mid-Hip becomes `(0,0,0)`.
   - **Step B (Scaling):** Calculate the 'Torso Length' (distance between Mid-Shoulder and Mid-Hip). Divide all translated coordinates by this Torso Length.
   - Create a `normalized_landmarks` dictionary with these final values. This ensures coordinates represent relative body proportions, unaffected by actual height or camera distance.

# Expected Output (JSON Schema)
The function must return a Python Dictionary (convertible to JSON) exactly matching this schema:

```json
{
  "fps": 30.0,
  "total_frames": 1800,
  "frames": [
    {
      "frame_index": 0,
      "time_sec": 0.0,
      "landmarks": {
        "left_shoulder": {"x": 0.52, "y": 0.31, "z": -0.15, "visibility": 0.99},
        // ... all 33 landmarks
      },
      "normalized_landmarks": {
        "left_shoulder": {"x": -0.2, "y": 0.8, "z": -0.1} 
        // ... all 33 scaled & translated landmarks relative to Mid-Hip
      }
    }
  ]
}