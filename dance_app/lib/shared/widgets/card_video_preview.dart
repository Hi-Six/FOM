import 'dart:io';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

/// Muted looping preview (asset, local file, or network URL).
class CardVideoPreview extends StatefulWidget {
  final String videoUrl;
  /// When null, fills available space from parent constraints.
  final double? height;
  final BorderRadius borderRadius;

  const CardVideoPreview({
    super.key,
    required this.videoUrl,
    this.height = 180,
    this.borderRadius = const BorderRadius.vertical(top: Radius.circular(16)),
  });

  @override
  State<CardVideoPreview> createState() => _CardVideoPreviewState();
}

class _CardVideoPreviewState extends State<CardVideoPreview> {
  VideoPlayerController? _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initController();
  }

  @override
  void didUpdateWidget(CardVideoPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.videoUrl != widget.videoUrl) {
      _controller?.dispose();
      _controller = null;
      _error = null;
      _initController();
    }
  }

  VideoPlayerController _createController(String path) {
    final normalized =
        path.startsWith('file://') ? path.replaceFirst('file://', '') : path;
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      return VideoPlayerController.networkUrl(Uri.parse(normalized));
    }
    if (normalized.startsWith('video_data/')) {
      return VideoPlayerController.asset(normalized);
    }
    return VideoPlayerController.file(File(normalized));
  }

  Future<void> _initController() async {
    final path = widget.videoUrl;
    if (path.isEmpty) return;

    final controller = _createController(path);

    try {
      await controller.initialize();
      await controller.setLooping(true);
      await controller.setVolume(0);
      await controller.play();
      if (!mounted) {
        controller.dispose();
        return;
      }
      setState(() => _controller = controller);
    } catch (e) {
      controller.dispose();
      if (mounted) setState(() => _error = e.toString());
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;

    final videoChild = controller != null && controller.value.isInitialized
        ? FittedBox(
            fit: BoxFit.cover,
            clipBehavior: Clip.hardEdge,
            child: SizedBox(
              width: controller.value.size.width,
              height: controller.value.size.height,
              child: VideoPlayer(controller),
            ),
          )
        : _placeholder();

    return ClipRRect(
      borderRadius: widget.borderRadius,
      child: widget.height != null
          ? SizedBox(
              height: widget.height,
              width: double.infinity,
              child: videoChild,
            )
          : LayoutBuilder(
              builder: (context, constraints) => SizedBox(
                width: constraints.maxWidth,
                height: constraints.maxHeight,
                child: videoChild,
              ),
            ),
    );
  }

  Widget _placeholder() {
    if (_error != null) {
      return const Center(
        child: Icon(Icons.videocam_off_outlined, color: Colors.white38, size: 40),
      );
    }
    return const Center(
      child: SizedBox(
        width: 28,
        height: 28,
        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white38),
      ),
    );
  }
}

String formatDurationLabel(Duration duration) {
  final total = duration.inSeconds;
  final minutes = total ~/ 60;
  final seconds = total % 60;
  return '$minutes:${seconds.toString().padLeft(2, '0')}';
}
