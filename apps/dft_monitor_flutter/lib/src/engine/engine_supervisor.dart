import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import '../settings/app_settings.dart';

enum EngineStatus { stopped, starting, ready, error }

class EngineReady {
  const EngineReady({
    required this.baseUrl,
    required this.pid,
    required this.dataRoot,
    required this.configDir,
    required this.frozen,
  });

  factory EngineReady.fromJson(Map<String, dynamic> json) {
    return EngineReady(
      baseUrl: json['base_url'] as String,
      pid: (json['pid'] as num).toInt(),
      dataRoot: json['data_root'] as String,
      configDir: json['config_dir'] as String,
      frozen: json['frozen'] == true,
    );
  }

  final String baseUrl;
  final int pid;
  final String dataRoot;
  final String configDir;
  final bool frozen;
}

class EngineState {
  const EngineState({
    this.status = EngineStatus.stopped,
    this.ready,
    this.logs = const <String>[],
    this.error,
  });

  final EngineStatus status;
  final EngineReady? ready;
  final List<String> logs;
  final String? error;

  bool get isReady => status == EngineStatus.ready && ready != null;

  EngineState copyWith({
    EngineStatus? status,
    EngineReady? ready,
    List<String>? logs,
    String? error,
    bool clearError = false,
    bool clearReady = false,
  }) {
    return EngineState(
      status: status ?? this.status,
      ready: clearReady ? null : ready ?? this.ready,
      logs: logs ?? this.logs,
      error: clearError ? null : error ?? this.error,
    );
  }
}

final engineSupervisorProvider =
    StateNotifierProvider<EngineSupervisor, EngineState>((ref) {
  final supervisor = EngineSupervisor();
  ref.onDispose(supervisor.dispose);
  unawaited(supervisor.start());
  return supervisor;
});

class EngineSupervisor extends StateNotifier<EngineState> {
  EngineSupervisor() : super(const EngineState());

  Process? _process;
  StreamSubscription<String>? _stdoutSub;
  StreamSubscription<String>? _stderrSub;
  StreamSubscription<int>? _exitSub;
  String? _lastDataRoot;
  String? _lastEnginePath;

  Future<void> start({String? dataRoot, String? enginePath}) async {
    _debug('start requested status=${state.status.name}');
    if (state.status == EngineStatus.starting || state.isReady) return;

    state = state.copyWith(
      status: EngineStatus.starting,
      logs: const <String>[],
      clearError: true,
      clearReady: true,
    );

    try {
      final stored = await _storedLaunchOptions();
      final selectedDataRoot = dataRoot ?? _lastDataRoot ?? stored.dataRoot;
      final selectedEnginePath =
          enginePath ?? _lastEnginePath ?? stored.enginePath;
      final executable = selectedEnginePath ?? await _resolveEnginePath();
      _lastDataRoot = selectedDataRoot;
      _lastEnginePath = selectedEnginePath;
      final args = <String>[
        '--engine',
        '--host',
        '127.0.0.1',
        '--port',
        '0',
        '--print-ready-json',
        '--log-level',
        'warning',
        if (selectedDataRoot != null && selectedDataRoot.isNotEmpty) ...[
          '--data-root',
          selectedDataRoot,
        ],
      ];

      _addLog('starting $executable ${args.join(' ')}');
      _debug('starting $executable ${args.join(' ')}');
      final process = await Process.start(
        executable,
        args,
        runInShell: Platform.isWindows,
      );
      _process = process;
      _debug('engine process pid=${process.pid}');

      final ready = Completer<EngineReady>();
      _stdoutSub = process.stdout
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen((line) {
        _addLog(line);
        if (!ready.isCompleted) {
          final parsed = _tryReady(line);
          if (parsed != null) ready.complete(parsed);
        }
      });

      _stderrSub = process.stderr
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(_addLog);

      _exitSub = process.exitCode.asStream().listen((code) {
        _addLog('engine exited with code $code');
        if (!ready.isCompleted) {
          ready.completeError(StateError('engine exited with code $code'));
        }
        if (mounted) {
          state = state.copyWith(
            status: EngineStatus.stopped,
            error: code == 0 ? null : 'engine exited with code $code',
            clearReady: true,
          );
        }
      });

      final info = await ready.future.timeout(const Duration(seconds: 45));
      if (!mounted) return;
      _debug('engine ready base_url=${info.baseUrl}');
      state = state.copyWith(status: EngineStatus.ready, ready: info);
    } catch (error) {
      _debug('start failed: $error');
      await stop();
      if (!mounted) return;
      state = state.copyWith(status: EngineStatus.error, error: '$error');
    }
  }

  Future<void> restart({String? dataRoot, String? enginePath}) async {
    _lastDataRoot = dataRoot ?? _lastDataRoot;
    _lastEnginePath = enginePath ?? _lastEnginePath;
    await stop();
    await start(dataRoot: _lastDataRoot, enginePath: _lastEnginePath);
  }

  Future<void> stop() async {
    await _stdoutSub?.cancel();
    await _stderrSub?.cancel();
    await _exitSub?.cancel();
    _stdoutSub = null;
    _stderrSub = null;
    _exitSub = null;

    final process = _process;
    _process = null;
    if (process != null) {
      process.kill();
      try {
        await process.exitCode.timeout(const Duration(seconds: 5));
      } catch (_) {
        process.kill(ProcessSignal.sigkill);
      }
    }
    if (mounted) {
      state = state.copyWith(status: EngineStatus.stopped, clearReady: true);
    }
  }

  @override
  void dispose() {
    unawaited(stop());
    super.dispose();
  }

  EngineReady? _tryReady(String line) {
    try {
      final data = jsonDecode(line);
      if (data is Map<String, dynamic> && data['event'] == 'ready') {
        return EngineReady.fromJson(data);
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  Future<String> _resolveEnginePath() async {
    final env = Platform.environment['DFT_MONITOR_ENGINE'];
    if (env != null && env.isNotEmpty && await File(env).exists()) return env;

    final exeName =
        Platform.isWindows ? 'dft-monitor-engine.exe' : 'dft-monitor-engine';
    final legacyName = Platform.isWindows ? 'dft-monitor.exe' : 'dft-monitor';
    final exeDir = p.dirname(Platform.resolvedExecutable);
    final candidates = <String>[
      p.join(exeDir, 'engine', exeName),
      p.join(exeDir, exeName),
      p.join(exeDir, 'engine', legacyName),
      p.join(exeDir, legacyName),
      p.join(exeDir, 'data', 'flutter_assets', 'assets', 'engine', exeName),
      p.join(exeDir, 'data', 'flutter_assets', 'assets', 'engine', legacyName),
      p.normalize(
          p.join(Directory.current.path, '..', '..', 'bin', 'dft-monitor')),
    ];
    for (final candidate in candidates) {
      if (await File(candidate).exists()) return candidate;
    }
    throw StateError(
      'No se encontro dft-monitor-engine. Define DFT_MONITOR_ENGINE.',
    );
  }

  Future<({String? dataRoot, String? enginePath})>
      _storedLaunchOptions() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return (
        dataRoot: _nonEmpty(prefs.getString(settingsDataRootKey)),
        enginePath: _nonEmpty(prefs.getString(settingsEnginePathKey)),
      );
    } catch (_) {
      return (dataRoot: null, enginePath: null);
    }
  }

  String? _nonEmpty(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    return value;
  }

  void _addLog(String line) {
    if (!mounted) return;
    _debug(line);
    final next = <String>[...state.logs, line];
    state = state.copyWith(
        logs: next.length > 500 ? next.sublist(next.length - 500) : next);
  }

  void _debug(String line) {
    final text = '${DateTime.now().toIso8601String()} $line';
    stderr.writeln(text);
    final workRoot = Platform.environment['DFT_WORK_ROOT'];
    if (workRoot == null || workRoot.isEmpty) return;
    try {
      final dir = Directory(p.join(workRoot, 'logs'));
      dir.createSync(recursive: true);
      File(p.join(dir.path, 'flutter-engine-supervisor.log')).writeAsStringSync(
        '$text\n',
        mode: FileMode.append,
      );
    } catch (_) {
      // Best-effort diagnostics only.
    }
  }
}
