class DanceVideo {
  final String id;
  final String title;
  final String genre;
  final String difficulty;
  final String thumbnailUrl;
  final String videoUrl;
  final String artist;
  final int durationSeconds;

  const DanceVideo({
    required this.id,
    required this.title,
    required this.genre,
    required this.difficulty,
    required this.thumbnailUrl,
    required this.videoUrl,
    required this.artist,
    required this.durationSeconds,
  });
}

class HomeRepository {
  static const _mockVideos = [
    DanceVideo(
      id: '1',
      title: '팝핑 기초',
      genre: '팝핑',
      difficulty: '초급',
      thumbnailUrl: '',
      videoUrl: '',
      artist: 'King Boogaloo',
      durationSeconds: 92,
    ),
    DanceVideo(
      id: '2',
      title: '브레이킹 입문',
      genre: '브레이킹',
      difficulty: '중급',
      thumbnailUrl: '',
      videoUrl: '',
      artist: 'B-Girl Steph',
      durationSeconds: 120,
    ),
    DanceVideo(
      id: '3',
      title: '록킹 그루브',
      genre: '록킹',
      difficulty: '초급',
      thumbnailUrl: '',
      videoUrl: '',
      artist: 'Funky Carlos',
      durationSeconds: 85,
    ),
    DanceVideo(
      id: '4',
      title: '왜킹 로열',
      genre: '왜킹',
      difficulty: '고급',
      thumbnailUrl: '',
      videoUrl: '',
      artist: 'Princess Diana',
      durationSeconds: 108,
    ),
    DanceVideo(
      id: '5',
      title: '하우스 풋워크',
      genre: '하우스',
      difficulty: '중급',
      thumbnailUrl: '',
      videoUrl: '',
      artist: 'DJ Footz',
      durationSeconds: 97,
    ),
  ];

  Future<List<DanceVideo>> fetchVideos() async {
    await Future.delayed(const Duration(milliseconds: 800));
    return _mockVideos;
  }
}
