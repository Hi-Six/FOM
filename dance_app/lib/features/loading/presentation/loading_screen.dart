import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_theme.dart';
import '../../studio/data/compare_session.dart';

class LoadingScreen extends StatefulWidget {
  final CompareSession? session;

  const LoadingScreen({super.key, this.session});

  @override
  State<LoadingScreen> createState() => _LoadingScreenState();
}

class _LoadingScreenState extends State<LoadingScreen>
    with TickerProviderStateMixin {
  static const _messages = [
    '관절 움직임 분석 중...',
    '리듬 정확도 계산 중...',
    '비트 타이밍 감지 중...',
    '레퍼런스와 비교 중...',
    '커리어 로드맵 생성 중...',
    'AI 분석 마무리 중...',
  ];

  int _msgIndex = 0;
  double _progress = 0;
  late final AnimationController _pulseCtrl;
  late final AnimationController _rotateCtrl;
  late final Timer _msgTimer;
  late final Timer _progressTimer;

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
      if (mounted) {
        setState(() => _msgIndex = (_msgIndex + 1) % _messages.length);
      }
    });

    _progressTimer = Timer.periodic(const Duration(milliseconds: 120), (_) {
      if (!mounted) return;
      setState(() {
        _progress = (_progress + 0.008).clamp(0.0, 0.95);
      });
    });

    // Navigate after ~7 seconds
    Future.delayed(const Duration(seconds: 7), () {
      if (mounted) {
        context.go('/feedback', extra: widget.session);
      }
    });
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _rotateCtrl.dispose();
    _msgTimer.cancel();
    _progressTimer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Spacer(flex: 2),
              // Dancing figure animation (Lottie placeholder)
              _DancingFigure(pulseCtrl: _pulseCtrl, rotateCtrl: _rotateCtrl),
              const SizedBox(height: 48),
              // Animated message
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
              const SizedBox(height: 32),
              // Progress bar
              Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'AI 분석 중',
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
                      valueColor: const AlwaysStoppedAnimation(AppColors.neonGreen),
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
                // Glow rings
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
                // Skeleton figure
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

    // Head
    canvas.drawCircle(Offset(cx, 18), 14, paint);
    // Neck
    canvas.drawLine(Offset(cx, 32), Offset(cx, 50), paint);
    // Torso
    canvas.drawLine(Offset(cx, 50), Offset(cx, 95), paint);
    // Shoulders
    canvas.drawLine(Offset(cx - 28, 58), Offset(cx + 28, 58), paint);
    // Left arm (animated)
    canvas.drawLine(
      Offset(cx - 28, 58),
      Offset(cx - 28 - armSwing, 85),
      paint,
    );
    canvas.drawLine(
      Offset(cx - 28 - armSwing, 85),
      Offset(cx - 28 - armSwing + 10, 110),
      paint,
    );
    // Right arm (animated opposite)
    canvas.drawLine(
      Offset(cx + 28, 58),
      Offset(cx + 28 + armSwing, 85),
      paint,
    );
    canvas.drawLine(
      Offset(cx + 28 + armSwing, 85),
      Offset(cx + 28 + armSwing - 10, 110),
      paint,
    );
    // Hips
    canvas.drawLine(Offset(cx - 20, 95), Offset(cx + 20, 95), paint);
    // Left leg (animated)
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
    // Right leg (animated opposite)
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

    // Joint dots
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

