class TalentRadarData {
  final double rom;
  final double power;
  final double rhythm;
  final double isolation;
  final double creativity;

  const TalentRadarData({
    required this.rom,
    required this.power,
    required this.rhythm,
    required this.isolation,
    required this.creativity,
  });
}

class CareerReport {
  final String genre;
  final int overallScore;
  final TalentRadarData radar;
  final String aiMessage;
  final List<String> recommendedCareers;

  const CareerReport({
    required this.genre,
    required this.overallScore,
    required this.radar,
    required this.aiMessage,
    required this.recommendedCareers,
  });
}

class ReportRepository {
  Future<CareerReport> fetchReport() async {
    await Future.delayed(const Duration(milliseconds: 600));
    return const CareerReport(
      genre: '팝핑',
      overallScore: 87,
      radar: TalentRadarData(
        rom: 0.78,
        power: 0.92,
        rhythm: 0.88,
        isolation: 0.95,
        creativity: 0.72,
      ),
      aiMessage:
          '너의 팝핑 타격감은 상위 10%야! 이 뛰어난 리듬감을 살려 안무가나 백업 댄서로 진로를 탐색해보는 건 어떨까? 지역 진로체험센터 프로그램을 추천해줄게.',
      recommendedCareers: ['백업 댄서', '안무가', '댄스 강사', '뮤직비디오 아티스트'],
    );
  }
}
