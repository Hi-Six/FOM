import 'dart:io';

import 'package:video_player/video_player.dart';

VideoPlayerController videoControllerFromPath(String path) {
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
