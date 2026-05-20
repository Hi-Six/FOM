/// 사용자 촬영본 + 레퍼런스(전문가) 영상 비교 세션.
class CompareSession {
  final String userVideoPath;
  final String referenceVideoPath;

  const CompareSession({
    required this.userVideoPath,
    required this.referenceVideoPath,
  });
}
