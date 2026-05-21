import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:http/http.dart' as http;

import '../../../core/config/api_config.dart';
import 'video_analyze_models.dart';

class VideoAnalyzeApiException implements Exception {
  final String message;
  final int? statusCode;

  const VideoAnalyzeApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

class VideoAnalyzeApi {
  static Future<bool> checkHealth() async {
    try {
      final res = await http
          .get(Uri.parse(ApiConfig.healthUrl))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return false;
      final body = jsonDecode(res.body) as Map<String, dynamic>;
      return body['status'] == 'ok';
    } catch (_) {
      return false;
    }
  }

  /// 로컬 mp4 → POST /video/analyze (user_video + reference_json).
  static Future<VideoAnalyzeResult> analyzeVideo({
    required String userVideoPath,
    required String referenceJson,
    required String expertVideoDisplayUrl,
    String? referenceVideoFilename,
    String? userAssetVideoUrl,
    bool autoDetectStart = true,
  }) async {
    List<int> bytes;
    try {
      bytes = await XFile(userVideoPath).readAsBytes();
    } catch (e) {
      throw VideoAnalyzeApiException('영상 파일을 읽을 수 없습니다: $e');
    }
    if (bytes.isEmpty) {
      throw VideoAnalyzeApiException('영상 파일이 비어 있습니다.');
    }

    final uri = Uri.parse(ApiConfig.videoAnalyzeUrl);
    final request = http.MultipartRequest('POST', uri)
      ..fields['reference_json'] = referenceJson
      ..fields['alignment_method'] = 'time'
      ..fields['auto_detect_start'] = autoDetectStart ? 'true' : 'false'
      ..fields['extraction_mode'] = 'full'
      ..fields['target_fps'] = '15';
    if (referenceVideoFilename != null && referenceVideoFilename.isNotEmpty) {
      request.fields['reference_video_filename'] = referenceVideoFilename;
    }
    request.files.add(
      http.MultipartFile.fromBytes(
        'user_video',
        bytes,
        filename: 'user.mp4',
      ),
    );

    final streamed = await request.send().timeout(const Duration(minutes: 20));
    final body = await http.Response.fromStream(streamed);

    if (body.statusCode != 200) {
      String detail = body.body;
      try {
        final err = jsonDecode(body.body);
        if (err is Map<String, dynamic>) {
          detail = err['detail']?.toString() ?? body.body;
        }
      } catch (_) {}
      throw VideoAnalyzeApiException(
        detail,
        statusCode: body.statusCode,
      );
    }

    final json = jsonDecode(body.body) as Map<String, dynamic>;
    return VideoAnalyzeResult.fromJson(
      json,
      expertVideoDisplayUrl: expertVideoDisplayUrl,
      userAssetVideoUrl: userAssetVideoUrl,
    );
  }

  /// [개발] 서버 `video_data/` MP4 + reference_json (`POST /video/analyze/by-name`).
  static Future<VideoAnalyzeResult> analyzeServerDevVideo({
    required String userVideoFilename,
    required String referenceJson,
    required String expertVideoDisplayUrl,
    String? referenceVideoFilename,
    String? userAssetVideoUrl,
    bool autoDetectStart = true,
  }) async {
    final uri = Uri.parse(ApiConfig.videoAnalyzeByNameUrl);
    final refVideo = referenceVideoFilename ?? userVideoFilename;
    final request = http.MultipartRequest('POST', uri)
      ..fields['user_video_filename'] = userVideoFilename
      ..fields['reference_json'] = referenceJson
      ..fields['reference_video_filename'] = refVideo
      ..fields['alignment_method'] = 'time'
      ..fields['auto_detect_start'] = autoDetectStart ? 'true' : 'false'
      ..fields['extraction_mode'] = 'full'
      ..fields['target_fps'] = '15';

    final streamed = await request.send().timeout(const Duration(minutes: 20));
    final body = await http.Response.fromStream(streamed);

    if (body.statusCode != 200) {
      String detail = body.body;
      try {
        final err = jsonDecode(body.body);
        if (err is Map<String, dynamic>) {
          detail = err['detail']?.toString() ?? body.body;
        }
      } catch (_) {}
      throw VideoAnalyzeApiException(
        detail,
        statusCode: body.statusCode,
      );
    }

    final json = jsonDecode(body.body) as Map<String, dynamic>;
    return VideoAnalyzeResult.fromJson(
      json,
      expertVideoDisplayUrl: expertVideoDisplayUrl,
      userServerVideoFilename: userVideoFilename,
      userAssetVideoUrl: userAssetVideoUrl,
    );
  }

  /// LLM 피드백 생성 (POST /video/analyze/feedback).
  static Future<Map<String, dynamic>> generateFeedback({
    required String userJson,
    required String referenceJson,
    String alignmentMethod = 'dtw',
    bool autoDetectStart = true,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/video/analyze/feedback');
    final request = http.MultipartRequest('POST', uri)
      ..fields['user_json'] = userJson
      ..fields['reference_json'] = referenceJson
      ..fields['alignment_method'] = alignmentMethod
      ..fields['auto_detect_start'] = autoDetectStart ? 'true' : 'false'
      ..fields['enable_accuracy'] = 'true'
      ..fields['enable_rom'] = 'true'
      ..fields['enable_creativity'] = 'true'
      ..fields['enable_isolation'] = 'true'
      ..fields['enable_power'] = 'true'
      ..fields['enable_rhythm'] = 'true';

    final streamed = await request.send().timeout(const Duration(minutes: 2));
    final body = await http.Response.fromStream(streamed);

    if (body.statusCode != 200) {
      String detail = body.body;
      try {
        final err = jsonDecode(body.body);
        if (err is Map<String, dynamic>) {
          detail = err['detail']?.toString() ?? body.body;
        }
      } catch (_) {}
      throw VideoAnalyzeApiException(
        detail,
        statusCode: body.statusCode,
      );
    }

    final json = jsonDecode(body.body) as Map<String, dynamic>;
    return json['feedback'] as Map<String, dynamic>? ?? {};
  }
}
