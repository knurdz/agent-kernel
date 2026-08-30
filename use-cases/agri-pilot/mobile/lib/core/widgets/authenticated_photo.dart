import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/env.dart';
import '../network/dio_client.dart';

/// Loads JWT-protected plant observation photos via Dio.
class AuthenticatedPhoto extends ConsumerStatefulWidget {
  const AuthenticatedPhoto({
    super.key,
    required this.photoUrl,
    this.localFile,
    this.height,
    this.width,
    this.fit = BoxFit.cover,
    this.borderRadius,
    this.onTap,
  });

  final String? photoUrl;
  final File? localFile;
  final double? height;
  final double? width;
  final BoxFit fit;
  final BorderRadius? borderRadius;
  final VoidCallback? onTap;

  @override
  ConsumerState<AuthenticatedPhoto> createState() => _AuthenticatedPhotoState();
}

class _AuthenticatedPhotoState extends ConsumerState<AuthenticatedPhoto> {
  Uint8List? _bytes;
  var _loading = false;
  var _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(AuthenticatedPhoto oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.photoUrl != widget.photoUrl || oldWidget.localFile != widget.localFile) {
      _load();
    }
  }

  String? _resolveUrl() {
    final path = widget.photoUrl;
    if (path == null || path.isEmpty) return null;
    if (path.startsWith('http')) return path;
    return '${Env.apiBaseUrl}$path';
  }

  Future<void> _load() async {
    if (widget.localFile != null) {
      setState(() {
        _bytes = null;
        _failed = false;
        _loading = false;
      });
      return;
    }
    final url = _resolveUrl();
    if (url == null) {
      setState(() {
        _bytes = null;
        _failed = true;
        _loading = false;
      });
      return;
    }
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final dio = ref.read(dioProvider);
      final resp = await dio.get<List<int>>(
        url,
        options: Options(responseType: ResponseType.bytes),
      );
      if (!mounted) return;
      setState(() {
        _bytes = Uint8List.fromList(resp.data ?? []);
        _loading = false;
        _failed = _bytes!.isEmpty;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _bytes = null;
        _loading = false;
        _failed = true;
      });
    }
  }

  Widget _placeholder(ThemeData theme) {
    return Container(
      height: widget.height,
      width: widget.width,
      color: theme.colorScheme.surfaceContainerHighest,
      alignment: Alignment.center,
      child: _loading
          ? const SizedBox(width: 28, height: 28, child: CircularProgressIndicator(strokeWidth: 2))
          : Icon(Icons.eco_outlined, size: 40, color: theme.colorScheme.onSurfaceVariant),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget child;
    if (widget.localFile != null) {
      child = Image.file(widget.localFile!, height: widget.height, width: widget.width, fit: widget.fit);
    } else if (_bytes != null && !_failed) {
      child = Image.memory(_bytes!, height: widget.height, width: widget.width, fit: widget.fit);
    } else {
      child = _placeholder(theme);
    }

    if (widget.borderRadius != null) {
      child = ClipRRect(borderRadius: widget.borderRadius!, child: child);
    }
    if (widget.onTap != null) {
      child = InkWell(onTap: widget.onTap, child: child);
    }
    return child;
  }
}
