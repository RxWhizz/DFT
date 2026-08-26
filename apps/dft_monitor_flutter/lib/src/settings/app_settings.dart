import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

const settingsDataRootKey = 'monitor.data_root';
const settingsEnginePathKey = 'monitor.engine_path';

class AppSettings {
  const AppSettings({
    this.loaded = false,
    this.dataRoot,
    this.enginePath,
  });

  final bool loaded;
  final String? dataRoot;
  final String? enginePath;

  String? get workRoot {
    final value = Platform.environment['DFT_WORK_ROOT'];
    return value == null || value.isEmpty ? null : value;
  }

  String? get logsDir {
    final root = workRoot;
    return root == null ? null : p.join(root, 'logs');
  }

  AppSettings copyWith({
    bool? loaded,
    String? dataRoot,
    String? enginePath,
    bool clearDataRoot = false,
    bool clearEnginePath = false,
  }) {
    return AppSettings(
      loaded: loaded ?? this.loaded,
      dataRoot: clearDataRoot ? null : dataRoot ?? this.dataRoot,
      enginePath: clearEnginePath ? null : enginePath ?? this.enginePath,
    );
  }
}

final appSettingsProvider =
    StateNotifierProvider<AppSettingsController, AppSettings>((ref) {
  return AppSettingsController();
});

class AppSettingsController extends StateNotifier<AppSettings> {
  AppSettingsController() : super(const AppSettings()) {
    _load();
  }

  Future<void> setDataRoot(String? path) async {
    final prefs = await SharedPreferences.getInstance();
    if (path == null || path.trim().isEmpty) {
      await prefs.remove(settingsDataRootKey);
      state = state.copyWith(clearDataRoot: true);
      return;
    }
    await prefs.setString(settingsDataRootKey, path);
    state = state.copyWith(dataRoot: path);
  }

  Future<void> setEnginePath(String? path) async {
    final prefs = await SharedPreferences.getInstance();
    if (path == null || path.trim().isEmpty) {
      await prefs.remove(settingsEnginePathKey);
      state = state.copyWith(clearEnginePath: true);
      return;
    }
    await prefs.setString(settingsEnginePathKey, path);
    state = state.copyWith(enginePath: path);
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    state = AppSettings(
      loaded: true,
      dataRoot: _nonEmpty(prefs.getString(settingsDataRootKey)),
      enginePath: _nonEmpty(prefs.getString(settingsEnginePathKey)),
    );
  }

  String? _nonEmpty(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    return value;
  }
}
