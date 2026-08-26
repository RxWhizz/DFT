import '../api/errors.dart';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;

import '../engine/engine_supervisor.dart';
import '../settings/app_settings.dart';

class DiagnosticsView extends ConsumerWidget {
  const DiagnosticsView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final engine = ref.watch(engineSupervisorProvider);
    final supervisor = ref.read(engineSupervisorProvider.notifier);
    final settings = ref.watch(appSettingsProvider);
    final settingsController = ref.read(appSettingsProvider.notifier);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text('Diagnóstico', style: Theme.of(context).textTheme.titleLarge),
            OutlinedButton.icon(
              onPressed: settings.loaded
                  ? () => _pickDataRoot(
                      context, settings, settingsController, supervisor)
                  : null,
              icon: const Icon(Icons.folder_open),
              label: const Text('Datos'),
            ),
            OutlinedButton.icon(
              onPressed: settings.loaded
                  ? () => _pickEngine(
                      context, settings, settingsController, supervisor)
                  : null,
              icon: const Icon(Icons.memory_outlined),
              label: const Text('Motor'),
            ),
            if (settings.logsDir != null)
              OutlinedButton.icon(
                onPressed: () => _openPath(context, settings.logsDir!),
                icon: const Icon(Icons.folder_copy_outlined),
                label: const Text('Registros'),
              ),
            OutlinedButton.icon(
              onPressed: engine.status == EngineStatus.starting
                  ? null
                  : () => supervisor.restart(
                        dataRoot: settings.dataRoot,
                        enginePath: settings.enginePath,
                      ),
              icon: const Icon(Icons.restart_alt),
              label: const Text('Reiniciar motor'),
            ),
            OutlinedButton.icon(
              onPressed: engine.status == EngineStatus.stopped
                  ? null
                  : () => supervisor.stop(),
              icon: const Icon(Icons.stop),
              label: const Text('Detener'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (engine.error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(engine.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 980 ? 2 : 1;
            final cardWidth =
                (constraints.maxWidth - (columns - 1) * 12) / columns;
            return Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                SizedBox(
                  width: cardWidth,
                  child: _InfoCard(
                    title: 'Motor',
                    lines: [
                      _InfoLine('Estado', engine.status.name),
                      _InfoLine('PID', engine.ready?.pid.toString() ?? '-'),
                      _InfoLine('URL', engine.ready?.baseUrl ?? '-'),
                      _InfoLine(
                          'Binario',
                          settings.enginePath ??
                              Platform.environment['DFT_MONITOR_ENGINE'] ??
                              'auto'),
                    ],
                  ),
                ),
                SizedBox(
                  width: cardWidth,
                  child: _InfoCard(
                    title: 'Datos',
                    lines: [
                      _InfoLine('Seleccionado', settings.dataRoot ?? '-'),
                      _InfoLine('Activo', engine.ready?.dataRoot ?? '-'),
                      _InfoLine(
                          'Config',
                          engine.ready?.configDir ??
                              Platform.environment['DFT_MONITOR_CONFIG_DIR'] ??
                              '-'),
                      _InfoLine('Logs', settings.logsDir ?? '-'),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
        const SizedBox(height: 12),
        Expanded(
          child: Card(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(12),
              child: SelectableText(
                engine.logs.join('\n'),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _pickDataRoot(
    BuildContext context,
    AppSettings settings,
    AppSettingsController settingsController,
    EngineSupervisor supervisor,
  ) async {
    final selected = await FilePicker.platform.getDirectoryPath(
      dialogTitle: 'Datos',
      initialDirectory: settings.dataRoot,
    );
    if (selected == null) return;
    await settingsController.setDataRoot(selected);
    await supervisor.restart(
        dataRoot: selected, enginePath: settings.enginePath);
  }

  Future<void> _pickEngine(
    BuildContext context,
    AppSettings settings,
    AppSettingsController settingsController,
    EngineSupervisor supervisor,
  ) async {
    final initial =
        settings.enginePath == null ? null : p.dirname(settings.enginePath!);
    final selected = await FilePicker.platform.pickFiles(
      dialogTitle: 'Motor',
      initialDirectory: initial,
      withData: false,
    );
    final path = selected?.files.single.path;
    if (path == null) return;
    await settingsController.setEnginePath(path);
    await supervisor.restart(dataRoot: settings.dataRoot, enginePath: path);
  }

  Future<void> _openPath(BuildContext context, String path) async {
    try {
      if (Platform.isWindows) {
        await Process.start('explorer.exe', [path]);
      } else if (Platform.isMacOS) {
        await Process.start('open', [path]);
      } else {
        await Process.start('xdg-open', [path]);
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
      }
    }
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.title, required this.lines});

  final String title;
  final List<_InfoLine> lines;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title.toUpperCase(),
                style: Theme.of(context).textTheme.labelSmall),
            const SizedBox(height: 8),
            for (final line in lines) line,
          ],
        ),
      ),
    );
  }
}

class _InfoLine extends StatelessWidget {
  const _InfoLine(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
              width: 96,
              child: Text(label, style: Theme.of(context).textTheme.bodySmall)),
          Expanded(
            child: SelectableText(
              value,
              style: const TextStyle(fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}
