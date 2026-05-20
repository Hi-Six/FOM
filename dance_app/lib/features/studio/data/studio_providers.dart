import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../home/data/home_repository.dart';
import 'compare_session.dart';

/// Home에서 선택한 챌린지(레퍼런스) 영상.
final selectedChallengeProvider = StateProvider<DanceVideo?>((ref) => null);

/// 동기 촬영으로 저장된 사용자 영상 로컬 경로.
final userVideoPathProvider = StateProvider<String?>((ref) => null);

/// 사용자 vs 레퍼런스 비교 세션 (촬영 완료 후 분석용).
final compareSessionProvider = StateProvider<CompareSession?>((ref) => null);
