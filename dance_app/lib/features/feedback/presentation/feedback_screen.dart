import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/app_theme.dart';
import '../../../shared/widgets/neon_badge.dart';

class FeedbackScreen extends StatefulWidget {
  final String? videoPath;

  const FeedbackScreen({super.key, this.videoPath});

  @override
  State<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends State<FeedbackScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _skeletonCtrl;
  double _timelinePos = 0.4;

  static const _mistakePositions = [0.15, 0.38, 0.62, 0.81];

  @override
  void initState() {
    super.initState();
    _skeletonCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
  }

  @override
  void dispose() {
    _skeletonCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_rounded, color: AppColors.textPrimary),
          onPressed: () => context.go('/home'),
        ),
        title: const Text(
          'AI 피드백',
          style: TextStyle(
            color: AppColors.neonGreen,
            fontSize: 16,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.5,
          ),
        ),
        centerTitle: true,
        actions: [
          TextButton(
            onPressed: () => context.go('/report'),
            child: const Text(
              '리포트 →',
              style: TextStyle(
                color: AppColors.neonPurple,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // Video + skeleton overlay
            _VideoWithSkeleton(ctrl: _skeletonCtrl),
            const SizedBox(height: 16),
            // Timeline
            _TimelineBar(
              position: _timelinePos,
              mistakes: _mistakePositions,
              onChanged: (v) => setState(() => _timelinePos = v),
            ),
            const SizedBox(height: 24),
            // Score indicators
            Row(
              children: [
                Expanded(
                  child: _ScoreCircle(
                    label: '리듬\n정확도',
                    value: 0.85,
                    color: AppColors.neonGreen,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _ScoreCircle(
                    label: '포즈\n일치도',
                    value: 0.90,
                    color: AppColors.neonPurple,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _ScoreCircle(
                    label: '종합\n점수',
                    value: 0.87,
                    color: AppColors.neonBlue,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            // Mistake list
            _MistakeList(),
            const SizedBox(height: 24),
            // CTA
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => context.go('/report'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.neonPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                child: const Text(
                  '커리어 리포트 보기 →',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}

class _VideoWithSkeleton extends StatelessWidget {
  final AnimationController ctrl;

  const _VideoWithSkeleton({required this.ctrl});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: AspectRatio(
        aspectRatio: 9 / 16,
        child: Stack(
          fit: StackFit.expand,
          children: [
            Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.neonPurple.withValues(alpha: 0.15),
                    AppColors.background,
                    AppColors.neonGreen.withValues(alpha: 0.1),
                  ],
                ),
              ),
              child: const Center(
                child: Text('🎬', style: TextStyle(fontSize: 64)),
              ),
            ),
            AnimatedBuilder(
              animation: ctrl,
              builder: (ctx, child) => CustomPaint(
                painter: _OverlaySkeletonPainter(phase: ctrl.value),
              ),
            ),
            // Play/pause overlay hint
            Positioned(
              right: 12,
              bottom: 12,
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.5),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.pause_rounded,
                  color: Colors.white,
                  size: 20,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OverlaySkeletonPainter extends CustomPainter {
  final double phase;

  _OverlaySkeletonPainter({required this.phase});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.neonGreen.withValues(alpha: 0.8)
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final dotPaint = Paint()
      ..color = AppColors.neonGreen
      ..style = PaintingStyle.fill;

    final cx = size.width / 2;
    final baseY = size.height * 0.25;
    final scale = size.height / 400;
    final arm = math.sin(phase * 2 * math.pi) * 18 * scale;
    final leg = math.sin(phase * 2 * math.pi) * 14 * scale;

    void line(Offset a, Offset b) => canvas.drawLine(a, b, paint);
    void dot(Offset p) => canvas.drawCircle(p, 4 * scale, dotPaint);

    final head = Offset(cx, baseY);
    final neck = Offset(cx, baseY + 22 * scale);
    final hip = Offset(cx, baseY + 80 * scale);
    final lShoulder = Offset(cx - 26 * scale, baseY + 30 * scale);
    final rShoulder = Offset(cx + 26 * scale, baseY + 30 * scale);
    final lElbow = Offset(cx - 26 * scale - arm, baseY + 58 * scale);
    final rElbow = Offset(cx + 26 * scale + arm, baseY + 58 * scale);
    final lHand = Offset(cx - 26 * scale - arm + 10 * scale, baseY + 82 * scale);
    final rHand = Offset(cx + 26 * scale + arm - 10 * scale, baseY + 82 * scale);
    final lKnee = Offset(cx - 18 * scale + leg, baseY + 118 * scale);
    final rKnee = Offset(cx + 18 * scale - leg, baseY + 118 * scale);
    final lFoot = Offset(cx - 18 * scale + leg - 8 * scale, baseY + 152 * scale);
    final rFoot = Offset(cx + 18 * scale - leg + 8 * scale, baseY + 152 * scale);

    canvas.drawCircle(head, 14 * scale, paint);
    line(neck, hip);
    line(lShoulder, rShoulder);
    line(lShoulder, lElbow);
    line(lElbow, lHand);
    line(rShoulder, rElbow);
    line(rElbow, rHand);
    line(Offset(cx - 18 * scale, baseY + 80 * scale), Offset(cx + 18 * scale, baseY + 80 * scale));
    line(Offset(cx - 18 * scale, baseY + 80 * scale), lKnee);
    line(lKnee, lFoot);
    line(Offset(cx + 18 * scale, baseY + 80 * scale), rKnee);
    line(rKnee, rFoot);

    for (final p in [neck, hip, lShoulder, rShoulder, lElbow, rElbow, lKnee, rKnee]) {
      dot(p);
    }
  }

  @override
  bool shouldRepaint(_OverlaySkeletonPainter old) => old.phase != phase;
}

class _TimelineBar extends StatelessWidget {
  final double position;
  final List<double> mistakes;
  final ValueChanged<double> onChanged;

  const _TimelineBar({
    required this.position,
    required this.mistakes,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              '타임라인',
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.8,
              ),
            ),
            Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: AppColors.error,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 4),
                const Text(
                  '미스 타이밍',
                  style: TextStyle(color: AppColors.textSecondary, fontSize: 11),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 8),
        LayoutBuilder(
          builder: (context, constraints) {
            final width = constraints.maxWidth;
            return GestureDetector(
              onHorizontalDragUpdate: (d) {
                onChanged((d.localPosition.dx / width).clamp(0, 1));
              },
              child: SizedBox(
                height: 40,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Container(
                      height: 6,
                      decoration: BoxDecoration(
                        color: AppColors.divider,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: FractionallySizedBox(
                        widthFactor: position,
                        child: Container(
                          height: 6,
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [AppColors.neonGreen, AppColors.neonBlue],
                            ),
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                      ),
                    ),
                    // Mistake dots
                    for (final m in mistakes)
                      Positioned(
                        left: width * m - 5,
                        child: Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: AppColors.error,
                            shape: BoxShape.circle,
                            border: Border.all(color: AppColors.background, width: 1.5),
                          ),
                        ),
                      ),
                    // Scrubber
                    Positioned(
                      left: width * position - 8,
                      child: Container(
                        width: 16,
                        height: 16,
                        decoration: const BoxDecoration(
                          color: AppColors.neonGreen,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}

class _ScoreCircle extends StatelessWidget {
  final String label;
  final double value;
  final Color color;

  const _ScoreCircle({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          SizedBox(
            width: 64,
            height: 64,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CircularProgressIndicator(
                  value: value,
                  backgroundColor: AppColors.divider,
                  valueColor: AlwaysStoppedAnimation(color),
                  strokeWidth: 6,
                ),
                Text(
                  '${(value * 100).toInt()}%',
                  style: TextStyle(
                    color: color,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 11,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }
}

class _MistakeList extends StatelessWidget {
  static const _items = [
    ('0:15', '왼팔 타이밍 0.3초 늦음', '팝 타이밍'),
    ('0:38', '무릎 각도 미세 조정 필요', '포즈 매치'),
    ('1:02', '비트 히팅 강도 부족', '리듬 정확도'),
    ('1:21', '웨이브 동작 연결 끊김', '플로우'),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '교정 포인트',
          style: TextStyle(
            color: AppColors.textSecondary,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
        ),
        const SizedBox(height: 12),
        for (final (time, desc, tag) in _items)
          Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.error.withValues(alpha: 0.25)),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.error.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    time,
                    style: const TextStyle(
                      color: AppColors.error,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    desc,
                    style: const TextStyle(color: AppColors.textPrimary, fontSize: 13),
                  ),
                ),
                NeonBadge(label: tag, color: AppColors.neonBlue),
              ],
            ),
          ),
      ],
    );
  }
}
