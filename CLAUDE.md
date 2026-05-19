# Role
You are an expert Flutter Developer and UI/UX Specialist. Your task is to scaffold and implement the frontend of an MVP app based on the provided specifications. 

# Project Context
- **Project:** AI-based Street Dance Level Judgment & Career Guide Platform (MVP).
- **Target Audience:** Teenagers (10s) who are highly sensitive to peer evaluation and need clear career direction. 
- **Core Value:** Providing a private, safe environment for dance practice, objective AI analysis, and customized career roadmaps (e.g., backup dancer, choreographer) without human intervention.
- **Vibe & Design System:** TikTok/Reels style. Fast-paced, intuitive UI. Default **Dark Mode** with vibrant **Neon accents** (e.g., Neon Green, Cyberpunk Purple) to fit the street dance culture.

# Constraints & Tech Stack
- **Framework:** Flutter (Latest version).
- **Authentication:** NO Auth (Skip login/signup completely for this 1-week MVP).
- **State Management:** Riverpod (or your recommended modern state management).
- **Routing:** go_router.
- **Key Packages to use:** `image_picker` (for gallery/camera), `video_player` (for playback & overlay), `fl_chart` (for radar charts), `lottie` (for loading animations).
- **Data Layer:** The app will eventually connect to a backend (e.g., FastAPI or Spring Boot). For now, implement **Mock Repositories** with simulated network delays (`Future.delayed`) returning dummy JSON data so the UI can be fully tested. Local data passing between screens should use simple state management or `shared_preferences`.

# App Structure & Navigation
Use a single `BottomNavigationBar` with 3 main tabs:
1. **Home (Challenge):** Explore reference videos.
2. **Studio (Action):** Upload/Shoot videos.
3. **Report (Result):** AI Feedback & Career Guide.

# Screen Specifications (Total 5 Screens)

## 1. Home Screen (Tab 1)
- **Layout:** Vertical scrolling list of dance reference videos (e.g., Popping Basics, Breaking Intro).
- **UI Elements:** Large video thumbnails, track title, and difficulty badge.
- **Action:** Tapping a thumbnail opens a bottom sheet or modal previewing the video with a prominent "Start Challenge" button that navigates to the Studio Screen.

## 2. Studio Screen (Tab 2)
- **Layout:** Split view or overlay. Top: small looping reference video. Bottom/Main: User's camera preview or upload UI.
- **Action:** Provide two clear buttons using `image_picker`: "Upload from Gallery" and "Shoot Video". 
- **Flow:** Once a video is selected, navigate immediately to the Loading Screen.

## 3. Loading Screen
- **Purpose:** Keep teenagers engaged while waiting for AI Vision and LLM processing.
- **UI Elements:** A cool dancing skeleton Lottie animation in the center. Dynamic text that changes every 2 seconds (e.g., "Analyzing joint movements...", "Calculating rhythm accuracy...", "Generating career roadmap...").

## 4. Feedback Screen (Navigated automatically after Loading)
- **Layout:** Focus on action correction. 
- **UI Elements:**
  - Main area: User's video playing with a simulated skeleton keypoint overlay (use `CustomPaint` over `video_player` to mock this).
  - Score Section: Circular progress indicators showing "Rhythm Accuracy (85%)" and "Pose Match (90%)".
  - Timeline: A horizontal bar under the video with red dots indicating mistakes (e.g., missed hit timing).

## 5. Career & Talent Report Screen (Tab 3 or accessed via Feedback Screen)
- **Layout:** Scrollable dashboard style.
- **UI Elements:**
  - **Talent Radar Chart:** Use `fl_chart` to display metrics like ROM (Range of Motion), Power, Rhythm, and Isolation.
  - **Career Guide Card:** A chat-bubble or modern card UI containing LLM-generated text. It should feel empathetic and encouraging. (Dummy text: "너의 팝핑 타격감은 상위 10%야! 이 뛰어난 리듬감을 살려 안무가나 백업 댄서로 진로를 탐색해보는 건 어떨까? 지역 진로체험센터 프로그램을 추천해줄게.")

# Tasks to Execute
1. Initialize the Flutter project with a clean feature-first architecture (e.g., `lib/features/home`, `lib/features/studio`, `lib/core/theme`).
2. Set up the Dark Theme with Neon accent colors.
3. Implement the `go_router` setup with the `BottomNavigationBar` layout.
4. Build the UI for the 5 screens described above using dummy data.
5. Provide the Mock Repository files that feed data to the Home and Report screens.

Please generate the code step-by-step, starting with the folder structure, theme setup, and router. Then proceed feature by feature. Let me know if you need any clarification before writing the code.