import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_theme.dart';
import '../../../shared/widgets/card_video_preview.dart';
import '../../../shared/widgets/neon_badge.dart';
import '../../studio/data/studio_providers.dart';
import '../data/home_repository.dart';

final homeVideosProvider = FutureProvider<List<DanceVideo>>((ref) {
  return HomeRepository().fetchVideos();
});

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncVideos = ref.watch(homeVideosProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '댄스\n챌린지',
                      style: Theme.of(context).textTheme.displayLarge?.copyWith(
                            foreground: Paint()
                              ..shader = const LinearGradient(
                                colors: [AppColors.neonGreen, AppColors.neonPurple],
                              ).createShader(const Rect.fromLTWH(0, 0, 200, 60)),
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '레퍼런스를 선택하고 도전해보세요',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
            ),
            asyncVideos.when(
              data: (videos) => SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _VideoCard(video: videos[index], ref: ref),
                  childCount: videos.length,
                ),
              ),
              loading: () => const SliverFillRemaining(
                child: Center(
                  child: CircularProgressIndicator(color: AppColors.neonGreen),
                ),
              ),
              error: (e, _) => SliverFillRemaining(
                child: Center(
                  child: Text('오류: $e', style: const TextStyle(color: AppColors.error)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _VideoCard extends StatelessWidget {
  final DanceVideo video;
  final WidgetRef ref;

  const _VideoCard({required this.video, required this.ref});

  Color get _difficultyColor {
    switch (video.difficulty) {
      case '초급':
        return AppColors.neonGreen;
      case '중급':
        return AppColors.neonBlue;
      case '고급':
        return AppColors.neonPurple;
      default:
        return AppColors.textSecondary;
    }
  }

  String get _durationLabel {
    final total = video.durationSeconds;
    return '${total ~/ 60}:${(total % 60).toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        ref.read(selectedChallengeProvider.notifier).state = video;
        _showChallengeSheet(context);
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.divider),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: 180,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (video.videoUrl.isNotEmpty)
                    CardVideoPreview(videoUrl: video.videoUrl)
                  else
                    DecoratedBox(
                      decoration: BoxDecoration(
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            AppColors.neonPurple.withValues(alpha: 0.3),
                            AppColors.neonGreen.withValues(alpha: 0.2),
                            AppColors.background,
                          ],
                        ),
                      ),
                      child: const Center(
                        child: Icon(Icons.music_note, color: Colors.white24, size: 64),
                      ),
                    ),
                  Positioned(
                    right: 12,
                    bottom: 12,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.7),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        _durationLabel,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    left: 12,
                    top: 12,
                    child: NeonBadge(label: video.genre, color: _difficultyColor),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          video.title,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          video.artist,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                    ),
                  ),
                  NeonBadge(label: video.difficulty, color: _difficultyColor),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showChallengeSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _ChallengeBottomSheet(video: video, ref: ref),
    );
  }
}

class _ChallengeBottomSheet extends StatelessWidget {
  final DanceVideo video;
  final WidgetRef ref;

  const _ChallengeBottomSheet({required this.video, required this.ref});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.divider,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text(video.title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text(video.artist, style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 20),
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: video.videoUrl.isNotEmpty
                ? CardVideoPreview(
                    videoUrl: video.videoUrl,
                    height: 120,
                    borderRadius: BorderRadius.circular(12),
                  )
                : Container(
                    height: 120,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12),
                      gradient: LinearGradient(
                        colors: [
                          AppColors.neonPurple.withValues(alpha: 0.25),
                          AppColors.neonGreen.withValues(alpha: 0.15),
                        ],
                      ),
                    ),
                    child: const Center(
                      child: Icon(Icons.play_circle_fill, color: AppColors.neonGreen, size: 56),
                    ),
                  ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () {
                ref.read(selectedChallengeProvider.notifier).state = video;
                ref.read(userVideoPathProvider.notifier).state = null;
                ref.read(compareSessionProvider.notifier).state = null;
                Navigator.pop(context);
                context.go('/studio');
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.neonGreen,
                foregroundColor: Colors.black,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: const Text(
                '챌린지 시작',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 1,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
        ],
      ),
    );
  }
}
