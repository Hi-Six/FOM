import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/config/api_config.dart';
import '../../../core/theme/app_theme.dart';
import '../../isolation/data/isolation_api.dart';
import '../../studio/data/compare_session.dart';
import '../../studio/data/studio_providers.dart';

class LoadingScreen extends ConsumerStatefulWidget {
  final CompareSession? session;

  const LoadingScreen({super.key, this.session});

  @override
  ConsumerState<LoadingScreen> createState() => _LoadingScreenState();
}

class _LoadingScreenState extends ConsumerState<LoadingScreen>
    with TickerProviderStateMixin {
  static const _messages = [
    'YOLO로 댄서 추적 중...',
    'MediaPipe Heavy 포즈 추출 중...',
    '기준 영상과 프레임 정렬 중...',
    'Isolation 점수 계산 중...',
  ];

  int _msgIndex = 0;
  double _progress = 0.05;
  String? _error;
  late final AnimationController _pulseCtrl;
  late final AnimationController _rotateCtrl;
  late final Timer _msgTimer;
  Timer? _progressTimer;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);
    _rotateCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();
    _msgTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (mounted && _error == null) {
        setState(() => _msgIndex = (_msgIndex + 1) % _messages.length);
      }
    });
    _progressTimer = Timer.periodic(const Duration(milliseconds: 400), (_) {
      if (!mounted || _error != null) return;
      setState(() {
        _progress = (_progress + 0.012).clamp(0.05, 0.92);
      });
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _runIsolationAnalyze());
  }

  Future<void> _runIsolationAnalyze() async {
    final session = widget.session;
    if (session == null || session.userVideoPath.isEmpty) {
      setState(() => _error = '촬영 세션이 없습니다. Studio에서 다시 촬영해 주세요.');
      return;
    }

    ref.read(isolationResultProvider.notifier).state = null;

    try {
      final ready = await IsolationApi.checkReady();
      if (!ready) {
        throw IsolationApiException(
          '서버 기준 데이터(ref.json)가 없습니다.\n'
          'backend1에서: python -m metrics.isolation.cli extract',
        );
      }

      final result = await IsolationApi.analyzeVideo(
        session.userVideoPath,
        autoDetectStart: true,
      );

      if (!mounted) return;
      ref.read(isolationResultProvider.notifier).state = result;
      setState(() => _progress = 1.0);
      await Future.delayed(const Duration(milliseconds: 400));
      if (mounted) {
        context.go('/feedback', extra: session);
      }
    } on IsolationApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) {
        setState(() {
          _error =
              '분석 요청 실패 (${ApiConfig.baseUrl})\n'
              '${ApiConfig.platformHint}\n'
              '실기기면: flutter run --dart-define=API_BASE_URL=http://<PC_IP>:8000\n'
              '$e';
        });
      }
    }
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _rotateCtrl.dispose();
    _msgTimer.cancel();
    _progressTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: _error != null ? _ErrorPanel(
              message: _error!,
              onRetry: () {
                setState(() {
                  _error = null;
                  _progress = 0.05;
                });
                _runIsolationAnalyze();
              },
              onHome: () => context.go('/home'),
            ) : Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Spacer(flex: 2),
                _DancingFigure(pulseCtrl: _pulseCtrl, rotateCtrl: _rotateCtrl),
                const SizedBox(height: 48),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 400),
                  child: Text(
                    _messages[_msgIndex],
                    key: ValueKey(_msgIndex),
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: AppColors.neonGreen,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.3,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '${ApiConfig.baseUrl}\n${ApiConfig.platformHint}',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 32),
                Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Isolation 분석',
                          style: TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                        Text(
                          '${(_progress * 100).toInt()}%',
                          style: const TextStyle(
                            color: AppColors.neonGreen,
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: _progress,
                        backgroundColor: AppColors.divider,
                        valueColor: const AlwaysStoppedAnimation(
                          AppColors.neonGreen,
                        ),
                        minHeight: 6,
                      ),
                    ),
                  ],
                ),
                const Spacer(flex: 3),
              ],
            ),
        ),
      ),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  final VoidCallback onHome;

  const _ErrorPanel({
    required this.message,
    required this.onRetry,
    required this.onHome,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.cloud_off_rounded, color: AppColors.error, size: 48),
        const SizedBox(height: 16),
        Text(
          message,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 24),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: onRetry,
            child: const Text('다시 시도'),
          ),
        ),
        const SizedBox(height: 8),
        TextButton(onPressed: onHome, child: const Text('홈으로')),
      ],
    );
  }
}

class _DancingFigure extends StatelessWidget {
  final AnimationController pulseCtrl;
  final AnimationController rotateCtrl;

  const _DancingFigure({required this.pulseCtrl, required this.rotateCtrl});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([pulseCtrl, rotateCtrl]),
      builder: (ctx, child) {
        final pulse = 0.9 + pulseCtrl.value * 0.2;
        return Transform.scale(
          scale: pulse,
          child: SizedBox(
            width: 200,
            height: 200,
            child: Stack(
              alignment: Alignment.center,
              children: [
                for (int i = 0; i < 3; i++)
                  Opacity(
                    opacity: (0.15 - i * 0.04).clamp(0, 1),
                    child: Container(
                      width: 140.0 + i * 30,
                      height: 140.0 + i * 30,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: AppColors.neonGreen,
                          width: 1.5,
                        ),
                      ),
                    ),
                  ),
                CustomPaint(
                  size: const Size(100, 160),
                  painter: _SkeletonPainter(
                    phase: rotateCtrl.value,
                    color: AppColors.neonGreen,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SkeletonPainter extends CustomPainter {
  final double phase;
  final Color color;

  _SkeletonPainter({required this.phase, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final dotPaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    final cx = size.width / 2;
    final armSwing = math.sin(phase * 2 * math.pi) * 20;
    final legSwing = math.sin(phase * 2 * math.pi) * 15;

    canvas.drawCircle(Offset(cx, 18), 14, paint);
    canvas.drawLine(Offset(cx, 32), Offset(cx, 50), paint);
    canvas.drawLine(Offset(cx, 50), Offset(cx, 95), paint);
    canvas.drawLine(Offset(cx - 28, 58), Offset(cx + 28, 58), paint);
    canvas.drawLine(Offset(cx - 28, 58), Offset(cx - 28 - armSwing, 85), paint);
    canvas.drawLine(
      Offset(cx - 28 - armSwing, 85),
      Offset(cx - 28 - armSwing + 10, 110),
      paint,
    );
    canvas.drawLine(Offset(cx + 28, 58), Offset(cx + 28 + armSwing, 85), paint);
    canvas.drawLine(
      Offset(cx + 28 + armSwing, 85),
      Offset(cx + 28 + armSwing - 10, 110),
      paint,
    );
    canvas.drawLine(Offset(cx - 20, 95), Offset(cx + 20, 95), paint);
    canvas.drawLine(
      Offset(cx - 20, 95),
      Offset(cx - 20 + legSwing, 130),
      paint,
    );
    canvas.drawLine(
      Offset(cx - 20 + legSwing, 130),
      Offset(cx - 20 + legSwing - 8, 158),
      paint,
    );
    canvas.drawLine(
      Offset(cx + 20, 95),
      Offset(cx + 20 - legSwing, 130),
      paint,
    );
    canvas.drawLine(
      Offset(cx + 20 - legSwing, 130),
      Offset(cx + 20 - legSwing + 8, 158),
      paint,
    );

    final joints = [
      Offset(cx, 18),
      Offset(cx, 50),
      Offset(cx, 95),
      Offset(cx - 28, 58),
      Offset(cx + 28, 58),
      Offset(cx - 28 - armSwing, 85),
      Offset(cx + 28 + armSwing, 85),
      Offset(cx - 20, 95),
      Offset(cx + 20, 95),
      Offset(cx - 20 + legSwing, 130),
      Offset(cx + 20 - legSwing, 130),
    ];
    for (final j in joints) {
      canvas.drawCircle(j, 4, dotPaint);
    }
  }

  @override
  bool shouldRepaint(_SkeletonPainter old) => old.phase != phase;
}
