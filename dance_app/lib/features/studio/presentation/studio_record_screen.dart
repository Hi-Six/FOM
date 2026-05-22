import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:video_player/video_player.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/video/video_source.dart';
import '../data/compare_session.dart';
import '../data/studio_providers.dart';

enum _RecordPhase { initializing, ready, countdown, recording, finishing, error }

class StudioRecordScreen extends ConsumerStatefulWidget {
  const StudioRecordScreen({super.key});

  @override
  ConsumerState<StudioRecordScreen> createState() => _StudioRecordScreenState();
}

class _StudioRecordScreenState extends ConsumerState<StudioRecordScreen> {
  CameraController? _camera;
  VideoPlayerController? _reference;
  _RecordPhase _phase = _RecordPhase.initializing;
  String? _errorMessage;
  bool _isRecording = false;
  int _countdown = 0;
  bool _stopRequested = false;

  @override
  void initState() {
    super.initState();
    _setup();
  }

  Future<void> _setup() async {
    final challenge = ref.read(selectedChallengeProvider);
    if (challenge == null || challenge.videoUrl.isEmpty) {
      setState(() {
        _phase = _RecordPhase.error;
        _errorMessage = '홈에서 챌린지를 먼저 선택해 주세요.';
      });
      return;
    }

    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        throw StateError('사용 가능한 카메라가 없습니다.');
      }

      final camera = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );

      final cameraController = CameraController(
        camera,
        ResolutionPreset.high,
        enableAudio: false,
      );
      final refController = videoControllerFromPath(challenge.videoUrl);

      await Future.wait([
        cameraController.initialize(),
        refController.initialize(),
      ]);

      await refController.setLooping(false);
      await refController.setVolume(1.0);
      await refController.pause();

      if (!mounted) {
        await cameraController.dispose();
        refController.dispose();
        return;
      }

      setState(() {
        _camera = cameraController;
        _reference = refController;
        _phase = _RecordPhase.ready;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _phase = _RecordPhase.error;
          _errorMessage = e.toString();
        });
      }
    }
  }

  Future<void> _beginCountdown() async {
    if (_phase != _RecordPhase.ready || _camera == null || _reference == null) {
      return;
    }

    setState(() {
      _phase = _RecordPhase.countdown;
      _countdown = 3;
    });

    for (var i = 3; i >= 1; i--) {
      if (!mounted) return;
      setState(() => _countdown = i);
      await Future.delayed(const Duration(seconds: 1));
    }

    if (!mounted) return;
    await _startSyncedCapture();
  }

  Future<void> _startSyncedCapture() async {
    final camera = _camera;
    final reference = _reference;
    if (camera == null || reference == null || !camera.value.isInitialized) {
      return;
    }

    setState(() {
      _phase = _RecordPhase.recording;
      _isRecording = true;
      _stopRequested = false;
    });

    reference.removeListener(_onReferenceProgress);
    await reference.pause();
    await reference.seekTo(Duration.zero);
    reference.addListener(_onReferenceProgress);

    await camera.startVideoRecording();
    await reference.play();
  }

  void _onReferenceProgress() {
    if (!_isRecording || _stopRequested) return;
    final reference = _reference;
    if (reference == null || !reference.value.isInitialized) return;

    final value = reference.value;
    final duration = value.duration;
    if (duration == Duration.zero) return;

    final nearEnd = value.position >= duration - const Duration(milliseconds: 200);
    final ended = !value.isPlaying && value.position > const Duration(milliseconds: 300);

    if (nearEnd || ended) {
      _stopSyncedCapture();
    }
  }

  Future<void> _stopSyncedCapture() async {
    if (_stopRequested) return;
    _stopRequested = true;

    final camera = _camera;
    final reference = _reference;
    if (camera == null) return;

    setState(() => _phase = _RecordPhase.finishing);

    reference?.removeListener(_onReferenceProgress);
    await reference?.pause();

    XFile? recorded;
    try {
      if (camera.value.isRecordingVideo) {
        recorded = await camera.stopVideoRecording();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _phase = _RecordPhase.error;
          _errorMessage = '녹화 저장 실패: $e';
          _isRecording = false;
        });
      }
      return;
    }

    if (!mounted) return;

    final challenge = ref.read(selectedChallengeProvider);
    if (recorded == null || challenge == null) {
      setState(() {
        _phase = _RecordPhase.error;
        _errorMessage = '녹화 파일을 찾을 수 없습니다.';
        _isRecording = false;
      });
      return;
    }

    final session = CompareSession.fromChallenge(
      challenge,
      userVideoPath: recorded.path,
    );

    ref.read(userVideoPathProvider.notifier).state = recorded.path;
    ref.read(compareSessionProvider.notifier).state = session;

    if (!mounted) return;
    context.pop();
  }

  @override
  void dispose() {
    _reference?.removeListener(_onReferenceProgress);
    _camera?.dispose();
    _reference?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final challenge = ref.watch(selectedChallengeProvider);

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: switch (_phase) {
          _RecordPhase.initializing => const Center(
              child: CircularProgressIndicator(color: AppColors.neonGreen),
            ),
          _RecordPhase.error => _ErrorView(
              message: _errorMessage ?? '알 수 없는 오류',
              onBack: () => context.pop(),
            ),
          _ => _RecordLayout(
              phase: _phase,
              countdown: _countdown,
              isRecording: _isRecording,
              challengeTitle: challenge?.title ?? '',
              camera: _camera,
              reference: _reference,
              onBack: () {
                if (_isRecording) {
                  _stopSyncedCapture();
                } else {
                  context.pop();
                }
              },
              onStart: _beginCountdown,
            ),
        },
      ),
    );
  }
}

class _RecordLayout extends StatelessWidget {
  final _RecordPhase phase;
  final int countdown;
  final bool isRecording;
  final String challengeTitle;
  final CameraController? camera;
  final VideoPlayerController? reference;
  final VoidCallback onBack;
  final VoidCallback onStart;

  const _RecordLayout({
    required this.phase,
    required this.countdown,
    required this.isRecording,
    required this.challengeTitle,
    required this.camera,
    required this.reference,
    required this.onBack,
    required this.onStart,
  });

  @override
  Widget build(BuildContext context) {
    final refReady = reference?.value.isInitialized ?? false;
    final camReady = camera?.value.isInitialized ?? false;

    return Stack(
      children: [
        Column(
          children: [
            _TopBar(
              title: challengeTitle,
              isRecording: isRecording,
              onBack: onBack,
            ),
            Expanded(
              flex: 5,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: ColoredBox(
                    color: AppColors.card,
                    child: refReady
                        ? _VideoFit(controller: reference!)
                        : const Center(
                            child: CircularProgressIndicator(
                              color: AppColors.neonPurple,
                              strokeWidth: 2,
                            ),
                          ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              flex: 5,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: ColoredBox(
                    color: AppColors.card,
                    child: camReady
                        ? CameraPreview(camera!)
                        : const Center(
                            child: CircularProgressIndicator(
                              color: AppColors.neonGreen,
                              strokeWidth: 2,
                            ),
                          ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
              child: Text(
                isRecording
                    ? '레퍼런스가 끝나면 촬영이 자동으로 종료됩니다'
                    : '레퍼런스와 동시에 재생·촬영됩니다',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            if (phase == _RecordPhase.ready)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                child: SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: camReady && refReady ? onStart : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.neonGreen,
                      foregroundColor: Colors.black,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    child: const Text(
                      '따라하며 촬영 시작',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
                    ),
                  ),
                ),
              )
            else if (phase == _RecordPhase.finishing)
              const Padding(
                padding: EdgeInsets.only(bottom: 24),
                child: CircularProgressIndicator(color: AppColors.neonGreen),
              )
            else
              const SizedBox(height: 56),
          ],
        ),
        if (phase == _RecordPhase.countdown)
          _CountdownOverlay(value: countdown),
      ],
    );
  }
}

class _TopBar extends StatelessWidget {
  final String title;
  final bool isRecording;
  final VoidCallback onBack;

  const _TopBar({
    required this.title,
    required this.isRecording,
    required this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 16, 8),
      child: Row(
        children: [
          IconButton(
            onPressed: onBack,
            icon: const Icon(Icons.close_rounded, color: Colors.white),
          ),
          Expanded(
            child: Text(
              title.isEmpty ? '따라하며 촬영' : title,
              style: Theme.of(context).textTheme.titleMedium,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (isRecording)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.red.withValues(alpha: 0.85),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.fiber_manual_record, color: Colors.white, size: 10),
                  SizedBox(width: 4),
                  Text(
                    'REC',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _VideoFit extends StatelessWidget {
  final VideoPlayerController controller;

  const _VideoFit({required this.controller});

  @override
  Widget build(BuildContext context) {
    return FittedBox(
      fit: BoxFit.cover,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        width: controller.value.size.width,
        height: controller.value.size.height,
        child: VideoPlayer(controller),
      ),
    );
  }
}

class _CountdownOverlay extends StatelessWidget {
  final int value;

  const _CountdownOverlay({required this.value});

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: Container(
        color: Colors.black54,
        alignment: Alignment.center,
        child: Text(
          '$value',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 96,
            fontWeight: FontWeight.w900,
          ),
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onBack;

  const _ErrorView({required this.message, required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.error_outline, color: AppColors.error, size: 48),
          const SizedBox(height: 16),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          ElevatedButton(onPressed: onBack, child: const Text('돌아가기')),
        ],
      ),
    );
  }
}
