import 'package:flutter/foundation.dart';

/// backend1 FastAPI (`uvicorn main:app --reload --host 0.0.0.0 --port 8000`)
///
/// 실기기(폰)는 PC와 같은 Wi‑Fi + PC IP 필수:
/// `flutter run --dart-define=API_BASE_URL=http://192.168.x.x:8000`
class ApiConfig {
  static String get baseUrl {
    const fromEnv = String.fromEnvironment('API_BASE_URL');
    if (fromEnv.isNotEmpty) return fromEnv;

    if (kIsWeb) return 'http://127.0.0.1:8000';

    // Android 에뮬레이터만 10.0.2.2 (실기기는 dart-define 으로 PC IP 지정)
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }

    // Windows / macOS / iOS 시뮬레이터
    return 'http://127.0.0.1:8000';
  }

  static String get isolationAnalyzeUrl => '$baseUrl/isolation/analyze';
  static String get isolationReadyUrl => '$baseUrl/isolation/ready';

  static String get platformHint {
    if (kIsWeb) return 'Web → localhost';
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'Android: 에뮬레이터=10.0.2.2, 실기기=PC IP (--dart-define)';
    }
    return 'Desktop/Simulator → 127.0.0.1';
  }
}
