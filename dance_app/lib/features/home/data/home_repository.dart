/// 챌린지 카드 1~5 ↔ `dance_app/video_data/cardN/` (mp4 + reference JSON).
class DanceVideo {
  final String id;
  final String title;
  final String genre;
  final String difficulty;
  final String thumbnailUrl;

  /// Flutter asset — `video_data/cardN/xxx.mp4`
  final String videoUrl;

  /// 서버 `video_json/` 파일명 (`POST /video/analyze` reference_json).
  final String referenceJson;

  /// 서버 `video_data/` MP4 파일명 (개발 by-name·전문가 스트리밍용).
  final String serverVideoFilename;

  final String artist;
  final int durationSeconds;

  const DanceVideo({
    required this.id,
    required this.title,
    required this.genre,
    required this.difficulty,
    required this.thumbnailUrl,
    required this.videoUrl,
    required this.referenceJson,
    required this.serverVideoFilename,
    required this.artist,
    required this.durationSeconds,
  });
}

class HomeRepository {
  static const challenges = <DanceVideo>[
    DanceVideo(
      id: '1',
      title: '팝핑 기초',
      genre: '팝핑',
      difficulty: '초급',
      thumbnailUrl: '',
      videoUrl: 'video_data/card1/gBR_sBM_c01_d06_mBR3_ch03.mp4',
      referenceJson: '20260521_134352_bed9b6d2.json',
      serverVideoFilename: 'gBR_sBM_c01_d06_mBR3_ch03.mp4',
      artist: 'King Boogaloo',
      durationSeconds: 92,
    ),
    DanceVideo(
      id: '2',
      title: '브레이킹 입문',
      genre: '브레이킹',
      difficulty: '중급',
      thumbnailUrl: '',
      videoUrl: 'video_data/card2/gBR_sBM_c01_d04_mBR3_ch03.mp4',
      referenceJson: '20260521_154323_979d22e6.json',
      serverVideoFilename: 'gBR_sBM_c01_d04_mBR3_ch03.mp4',
      artist: 'B-Girl Steph',
      durationSeconds: 97,
    ),
    DanceVideo(
      id: '3',
      title: '록킹 그루브',
      genre: '록킹',
      difficulty: '초급',
      thumbnailUrl: '',
      videoUrl: 'video_data/card3/gHO_sBM_c01_d19_mHO3_ch03.mp4',
      referenceJson: '20260521_154842_eee5efdc.json',
      serverVideoFilename: 'gHO_sBM_c01_d19_mHO3_ch03.mp4',
      artist: 'Funky Carlos',
      durationSeconds: 85,
    ),
    DanceVideo(
      id: '4',
      title: '왜킹 로열',
      genre: '왜킹',
      difficulty: '고급',
      thumbnailUrl: '',
      videoUrl: 'video_data/card4/gJB_sBM_c01_d07_mJB3_ch03.mp4',
      referenceJson: '20260521_155027_4acf1e1d.json',
      serverVideoFilename: 'gJB_sBM_c01_d07_mJB3_ch03.mp4',
      artist: 'Princess Diana',
      durationSeconds: 108,
    ),
    DanceVideo(
      id: '5',
      title: '하우스 풋워크',
      genre: '하우스',
      difficulty: '중급',
      thumbnailUrl: '',
      videoUrl: 'video_data/card5/gMH_sBM_c01_d24_mMH3_ch03.mp4',
      referenceJson: '20260521_155225_a8cc4d5b.json',
      serverVideoFilename: 'gMH_sBM_c01_d24_mMH3_ch03.mp4',
      artist: 'DJ Footz',
      durationSeconds: 97,
    ),
  ];

  Future<List<DanceVideo>> fetchVideos() async {
    await Future.delayed(const Duration(milliseconds: 800));
    return List<DanceVideo>.from(challenges);
  }
}
