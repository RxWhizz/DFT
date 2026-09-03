import '../api/errors.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';
import '../widgets/confirm_action.dart';

class DiscoveryView extends ConsumerStatefulWidget {
  const DiscoveryView({super.key});

  @override
  ConsumerState<DiscoveryView> createState() => _DiscoveryViewState();
}

class _DiscoveryViewState extends ConsumerState<DiscoveryView> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final status = ref.watch(discoveryStatusProvider);

    return AsyncPanel(
      value: status,
      builder: (data) => RefreshIndicator(
        onRefresh: () async => _refresh(),
        child: ListView(
          children: [
            _HeaderCard(
              data: data,
              busy: _busy,
              onInit: () => _init(context),
              onReset: data.backgroundRunning ? null : () => _reset(context),
              onDryRun: () => _runDry(context),
              onPrepareDft: data.state.status == 'dft_selected'
                  ? () => _prepareDft(context)
                  : null,
              onRun: () => _runFull(context),
              onPause: data.backgroundRunning ? () => _pause(context) : null,
              onResume: !data.backgroundRunning && data.state.status == 'paused'
                  ? () => _resume(context)
                  : null,
              onExport: () => _export(context),
            ),
            if (data.runnerStale) ...[
              const SizedBox(height: 12),
              _RunnerWarningCard(data: data),
            ],
            if (data.state.mlffWarning != null) ...[
              const SizedBox(height: 12),
              _MlffWarningCard(state: data.state),
            ],
            const SizedBox(height: 12),
            _SpaceConfigCard(canEdit: !data.backgroundRunning && !_busy),
            const SizedBox(height: 12),
            LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth >= 1080;
                final leftWidth = wide
                    ? (constraints.maxWidth * 0.34).clamp(420.0, 560.0)
                    : constraints.maxWidth;
                final info = _StateCard(data: data);
                final queue = _CandidateTableCard(
                  title: 'Cola DFT',
                  subtitle:
                      '${data.queue.length} candidatos listos para verificación PBE',
                  items: data.queue,
                  compact: true,
                );
                final frontier = _CandidateTableCard(
                  title: 'Frontera Pareto',
                  subtitle:
                      '${data.frontier.length} candidatos no dominados o de alta adquisición',
                  items: data.frontier,
                );

                if (!wide) {
                  return Column(
                    children: [
                      info,
                      const SizedBox(height: 12),
                      queue,
                      const SizedBox(height: 12),
                      frontier,
                    ],
                  );
                }
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: leftWidth, child: info),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        children: [queue, const SizedBox(height: 12), frontier],
                      ),
                    ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  void _refresh() {
    ref.invalidate(discoveryStatusProvider);
    ref.invalidate(discoveryConfigProvider);
    ref.invalidate(activityProvider);
    ref.invalidate(summaryProvider);
    ref.invalidate(batchesProvider);
    ref.invalidate(jobsProvider);
  }

  Future<void> _mutate(
    BuildContext context,
    Future<Object?> Function(DiscoveryActions actions) call, {
    String? success,
  }) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final actions = ref.read(discoveryActionsProvider);
      await call(actions);
      _refresh();
      if (success != null && context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(success)));
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _init(BuildContext context) async {
    await _mutate(
      context,
      (actions) => actions.init(),
      success: 'Ledger de descubrimiento cargado.',
    );
  }

  Future<void> _reset(BuildContext context) async {
    final ok = await confirmAction(
      context,
      title: 'Reiniciar criba',
      message:
          'Se regenerará el espacio químico y el ledger desde cero con la configuración actual. Las carpetas DFT anteriores permanecen en disco.',
      confirmLabel: 'Reiniciar',
    );
    if (!ok || !context.mounted) return;
    await _mutate(
      context,
      (actions) => actions.init(reset: true),
      success: 'Criba reiniciada desde el principio.',
    );
  }

  Future<void> _runDry(BuildContext context) async {
    await _mutate(
      context,
      (actions) => actions.run(
        startRunner: false,
        dryRun: true,
        useMlff: false,
        maxRounds: 1,
      ),
      success: 'Ronda preliminar calculada sin lanzar DFT.',
    );
  }

  Future<void> _prepareDft(BuildContext context) async {
    await _mutate(
      context,
      (actions) => actions.run(
        startRunner: false,
        dryRun: false,
        useMlff: false,
        maxRounds: 1,
      ),
      success: 'Jobs DFT preparados para la ronda activa.',
    );
  }

  Future<void> _runFull(BuildContext context) async {
    final ok = await confirmAction(
      context,
      title: 'Ejecutar protocolo',
      message:
          'El ciclo autónomo puede preparar y lanzar rondas DFT de 30 candidatos. Continúa solo si el entorno DFT local está listo.',
      confirmLabel: 'Ejecutar',
    );
    if (!ok) return;
    if (!context.mounted) return;
    await _mutate(
      context,
      (actions) => actions.run(startRunner: true, dryRun: false),
      success: 'Protocolo autónomo iniciado en segundo plano.',
    );
  }

  Future<void> _pause(BuildContext context) async {
    await _mutate(
      context,
      (actions) => actions.pause(),
      success: 'Protocolo pausado.',
    );
  }

  Future<void> _resume(BuildContext context) async {
    await _mutate(
      context,
      (actions) => actions.resume(),
      success: 'Protocolo reanudado.',
    );
  }

  Future<void> _export(BuildContext context) async {
    await _mutate(
      context,
      (actions) => actions.export(),
      success: 'Reporte y tablas de descubrimiento exportados.',
    );
  }

  void _showError(BuildContext context, Object error) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
  }
}

class _HeaderCard extends StatelessWidget {
  const _HeaderCard({
    required this.data,
    required this.busy,
    required this.onInit,
    required this.onReset,
    required this.onDryRun,
    required this.onRun,
    required this.onExport,
    this.onPrepareDft,
    this.onPause,
    this.onResume,
  });

  final DiscoveryStatus data;
  final bool busy;
  final VoidCallback onInit;
  final VoidCallback? onReset;
  final VoidCallback onDryRun;
  final VoidCallback? onPrepareDft;
  final VoidCallback onRun;
  final VoidCallback? onPause;
  final VoidCallback? onResume;
  final VoidCallback onExport;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            'Protocolo de Descubrimiento Autónomo',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(width: 10),
                          _StatusPill(
                            label: _statusLabel(data.state.status),
                            active: data.backgroundRunning,
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'ML criba todo el espacio viable, DFT verifica los mejores candidatos y el ledger permite continuar por rondas.',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
                if (data.background?.lastError != null)
                  Tooltip(
                    message: data.background!.lastError!,
                    child: Icon(
                      Icons.error_outline,
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _Metric(
                  label: 'Espacio visto',
                  value: '${data.seen} / ${data.total}',
                  subvalue: '${fmtNumber(data.percent, 1)} %',
                ),
                _Metric(
                  label: 'Viables ML',
                  value: '${data.counts['viable_ml'] ?? 0}',
                  subvalue: 'sobre reglas + surrogates',
                ),
                _Metric(
                  label: 'Ronda',
                  value: '${data.state.currentRound}',
                  subvalue: '${data.state.dftPerRound} DFT/ronda',
                ),
                _Metric(
                  label: 'Seleccionados',
                  value: '${data.selectedForDft}',
                  subvalue: 'para verificación',
                ),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: busy ? null : onInit,
                  icon: const Icon(Icons.playlist_add_check_circle_outlined),
                  label: const Text('Cargar ledger'),
                ),
                OutlinedButton.icon(
                  onPressed: busy ? null : onReset,
                  icon: const Icon(Icons.restart_alt_outlined),
                  label: const Text('Reiniciar criba'),
                ),
                OutlinedButton.icon(
                  onPressed: busy ? null : onDryRun,
                  icon: const Icon(Icons.visibility_outlined),
                  label: const Text('Previsualizar'),
                ),
                OutlinedButton.icon(
                  onPressed: busy ? null : onPrepareDft,
                  icon: const Icon(Icons.science_outlined),
                  label: const Text('Preparar DFT'),
                ),
                FilledButton.icon(
                  onPressed: busy ? null : onRun,
                  icon: const Icon(Icons.rocket_launch_outlined),
                  label: Text(busy ? '...' : 'Ejecutar protocolo'),
                ),
                if (onPause != null)
                  OutlinedButton.icon(
                    onPressed: busy ? null : onPause,
                    icon: const Icon(Icons.pause_circle_outline),
                    label: const Text('Pausar'),
                  ),
                if (onResume != null)
                  OutlinedButton.icon(
                    onPressed: busy ? null : onResume,
                    icon: const Icon(Icons.play_circle_outline),
                    label: const Text('Reanudar'),
                  ),
                TextButton.icon(
                  onPressed: busy ? null : onExport,
                  icon: const Icon(Icons.file_download_outlined),
                  label: const Text('Exportar'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Aviso de que la última criba corrió sin Tier 2.
///
/// Es ámbar, no rojo, y a propósito: la ronda SÍ avanzó, sólo que con menos
/// criba. Pintarlo como error haría que se ignorara un protocolo que está
/// funcionando; no pintarlo dejaría al usuario creyendo que hubo MLFF.
class _MlffWarningCard extends StatelessWidget {
  const _MlffWarningCard({required this.state});

  final DiscoveryState state;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: theme.colorScheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.science_outlined,
                color: theme.colorScheme.onTertiaryContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Cribado sin Tier 2 (MLFF/GNN)',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: theme.colorScheme.onTertiaryContainer,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    state.mlffError ?? 'El entorno MLFF no está disponible.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onTertiaryContainer,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    state.mlffRemediacion ??
                        'La ronda avanzó con Tier 0/1: se descartó menos material '
                            'del que se habría descartado con estabilidad MLFF.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onTertiaryContainer,
                    ),
                  ),
                  const SizedBox(height: 8),
                  FilledButton.tonalIcon(
                    onPressed: () => context.go('/entorno'),
                    icon: const Icon(Icons.build_outlined, size: 16),
                    label: const Text('Configurar entorno'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RunnerWarningCard extends StatelessWidget {
  const _RunnerWarningCard({required this.data});

  final DiscoveryStatus data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final counts = data.runner['status_counts'] is Map
        ? Map<String, dynamic>.from(data.runner['status_counts'] as Map)
        : const <String, dynamic>{};
    return Card(
      color: theme.colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.error_outline,
                color: theme.colorScheme.onErrorContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'DFT preparado, runner no activo',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    data.runnerError ??
                        'No hay procesos GPAW ni logs de cálculo para la ronda activa.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Jobs: ${counts.entries.map((e) => '${e.key} ${e.value}').join(' · ')}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SpaceConfigCard extends ConsumerStatefulWidget {
  const _SpaceConfigCard({required this.canEdit});

  final bool canEdit;

  @override
  ConsumerState<_SpaceConfigCard> createState() => _SpaceConfigCardState();
}

class _SpaceConfigCardState extends ConsumerState<_SpaceConfigCard> {
  final _aSites = TextEditingController();
  final _bSites = TextEditingController();
  final _xSites = TextEditingController();
  final _minFraction = TextEditingController();
  final _maxFraction = TextEditingController();
  final _fractionStep = TextEditingController();
  final _dftPerRound = TextEditingController();

  Map<String, bool> _modes = const {
    'pure': true,
    'A_mixed': true,
    'B_mixed': true,
    'X_mixed': true,
    'multi_mixed': false,
  };
  DiscoverySpaceConfig? _preview;
  String? _loadedSignature;
  bool _busy = false;

  @override
  void dispose() {
    _aSites.dispose();
    _bSites.dispose();
    _xSites.dispose();
    _minFraction.dispose();
    _maxFraction.dispose();
    _fractionStep.dispose();
    _dftPerRound.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(discoveryConfigProvider);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: AsyncPanel(
          value: config,
          builder: (data) {
            _hydrate(data);
            final preview = _preview?.preview ?? data.preview;
            final fractionValues = _preview?.fractionValues.isNotEmpty == true
                ? _preview!.fractionValues
                : data.fractionValues;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Espacio químico',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                    _StatusPill(
                      label: data.overrideSaved ? 'override activo' : 'base',
                      active: data.overrideSaved,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _ConfigTextField(
                      label: 'A cationes',
                      controller: _aSites,
                      enabled: widget.canEdit && !_busy,
                      width: 260,
                    ),
                    _ConfigTextField(
                      label: 'B cationes',
                      controller: _bSites,
                      enabled: widget.canEdit && !_busy,
                      width: 260,
                    ),
                    _ConfigTextField(
                      label: 'X aniones',
                      controller: _xSites,
                      enabled: widget.canEdit && !_busy,
                      width: 220,
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _ConfigTextField(
                      label: 'Fracción mínima',
                      controller: _minFraction,
                      enabled: widget.canEdit && !_busy,
                      numeric: true,
                    ),
                    _ConfigTextField(
                      label: 'Fracción máxima',
                      controller: _maxFraction,
                      enabled: widget.canEdit && !_busy,
                      numeric: true,
                    ),
                    _ConfigTextField(
                      label: 'Paso',
                      controller: _fractionStep,
                      enabled: widget.canEdit && !_busy,
                      numeric: true,
                    ),
                    _ConfigTextField(
                      label: 'DFT/ronda',
                      controller: _dftPerRound,
                      enabled: widget.canEdit && !_busy,
                      numeric: true,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final key in const [
                      'pure',
                      'A_mixed',
                      'B_mixed',
                      'X_mixed',
                      'multi_mixed',
                    ])
                      FilterChip(
                        selected: _modes[key] ?? false,
                        onSelected: widget.canEdit && !_busy
                            ? (value) => setState(() {
                                  _modes = {..._modes, key: value};
                                })
                            : null,
                        label: Text(_modeLabel(key)),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 14,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _MiniMetric(
                      label: 'Total generado',
                      value: '${preview?.totalGenerated ?? '-'}',
                    ),
                    _MiniMetric(
                      label: 'Viables físicos',
                      value: '${preview?.physicallyViable ?? '-'}',
                    ),
                    _MiniMetric(
                      label: 'Rechazados',
                      value: '${preview?.rejectedPhysical ?? '-'}',
                    ),
                    _MiniMetric(
                      label: 'Pesos',
                      value: '${fractionValues.length}',
                    ),
                    if (preview?.modeCounts.isNotEmpty == true)
                      Text(
                        _modeCountsText(preview!.modeCounts),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    OutlinedButton.icon(
                      onPressed: widget.canEdit && !_busy
                          ? () => _previewConfig(context, data)
                          : null,
                      icon: const Icon(Icons.analytics_outlined),
                      label: const Text('Previsualizar conteo'),
                    ),
                    OutlinedButton.icon(
                      onPressed: widget.canEdit && !_busy
                          ? () => _saveConfig(context, data)
                          : null,
                      icon: const Icon(Icons.save_outlined),
                      label: const Text('Guardar espacio'),
                    ),
                    FilledButton.icon(
                      onPressed: widget.canEdit && !_busy
                          ? () => _saveAndReset(context, data)
                          : null,
                      icon: const Icon(Icons.restart_alt_outlined),
                      label: Text(_busy ? '...' : 'Guardar y reiniciar'),
                    ),
                  ],
                ),
                if (data.overridePath != null) ...[
                  const SizedBox(height: 10),
                  SelectableText(
                    data.overridePath!,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            );
          },
        ),
      ),
    );
  }

  void _hydrate(DiscoverySpaceConfig config) {
    final signature = [
      config.aSites.join(','),
      config.bSites.join(','),
      config.xSites.join(','),
      config.minFraction,
      config.maxFraction,
      config.fractionStep,
      config.dftPerRound,
      config.modes.entries
          .map((entry) => '${entry.key}:${entry.value}')
          .join(','),
    ].join('|');
    if (_loadedSignature == signature) return;
    _aSites.text = config.aSites.join(', ');
    _bSites.text = config.bSites.join(', ');
    _xSites.text = config.xSites.join(', ');
    _minFraction.text = fmtNumber(config.minFraction, 4);
    _maxFraction.text = fmtNumber(config.maxFraction, 4);
    _fractionStep.text = fmtNumber(config.fractionStep, 4);
    _dftPerRound.text = '${config.dftPerRound}';
    _modes = Map<String, bool>.from(config.modes);
    _preview = config.preview == null ? null : config;
    _loadedSignature = signature;
  }

  DiscoverySpaceConfig _draft(DiscoverySpaceConfig base) {
    final modes = {
      'pure': _modes['pure'] ?? true,
      'A_mixed': _modes['A_mixed'] ?? true,
      'B_mixed': _modes['B_mixed'] ?? true,
      'X_mixed': _modes['X_mixed'] ?? true,
      'multi_mixed': _modes['multi_mixed'] ?? false,
    };
    return DiscoverySpaceConfig(
      aSites: _parseSpecies(_aSites.text),
      bSites: _parseSpecies(_bSites.text),
      xSites: _parseSpecies(_xSites.text),
      modes: modes,
      minFraction: _parseDouble(_minFraction.text),
      maxFraction: _parseDouble(_maxFraction.text),
      fractionStep: _parseDouble(_fractionStep.text),
      fractionValues: base.fractionValues,
      includeMultiMixed: modes['multi_mixed'] ?? false,
      dftPerRound: _parseInt(_dftPerRound.text),
      availableSpecies: base.availableSpecies,
      source: base.source,
      overridePath: base.overridePath,
      overrideSaved: base.overrideSaved,
    );
  }

  Future<void> _previewConfig(
    BuildContext context,
    DiscoverySpaceConfig base,
  ) async {
    await _mutateConfig(
      context,
      () async {
        final result = await ref
            .read(discoveryActionsProvider)
            .previewConfig(_draft(base));
        setState(() => _preview = result);
      },
    );
  }

  Future<void> _saveConfig(
    BuildContext context,
    DiscoverySpaceConfig base,
  ) async {
    await _mutateConfig(
      context,
      () async {
        final result =
            await ref.read(discoveryActionsProvider).saveConfig(_draft(base));
        setState(() => _preview = result);
        _invalidate();
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Espacio químico guardado.')),
          );
        }
      },
    );
  }

  Future<void> _saveAndReset(
    BuildContext context,
    DiscoverySpaceConfig base,
  ) async {
    final ok = await confirmAction(
      context,
      title: 'Guardar y reiniciar',
      message:
          'Se guardará el espacio químico y se regenerará el ledger desde cero. Las carpetas DFT anteriores permanecen en disco.',
      confirmLabel: 'Reiniciar',
    );
    if (!ok || !context.mounted) return;
    await _mutateConfig(
      context,
      () async {
        final actions = ref.read(discoveryActionsProvider);
        final result = await actions.saveConfig(_draft(base));
        await actions.init(reset: true);
        setState(() => _preview = result);
        _invalidate();
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
                content: Text('Espacio guardado y criba reiniciada.')),
          );
        }
      },
    );
  }

  Future<void> _mutateConfig(
    BuildContext context,
    Future<void> Function() action,
  ) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(mensajeDeError(error))),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _invalidate() {
    ref.invalidate(discoveryConfigProvider);
    ref.invalidate(discoveryStatusProvider);
    ref.invalidate(activityProvider);
  }
}

class _StateCard extends StatelessWidget {
  const _StateCard({required this.data});

  final DiscoveryStatus data;

  @override
  Widget build(BuildContext context) {
    final space = data.state.space;
    final screening = data.state.lastScreening;
    final prepared = data.state.lastPrepared;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Estado del ledger',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            _Line('Estado', _statusLabel(data.state.status)),
            _Line('Frontera', '${data.frontier.length} candidatos'),
            _Line('Cola DFT', '${data.queue.length} candidatos'),
            if (data.state.stopReason != null)
              _Line('Criterio de parada', data.state.stopReason!),
            const Divider(height: 24),
            _Line('Generados', '${_asInt(space['total_generated'])}'),
            _Line(
              'Físicamente viables',
              '${_asInt(space['physically_viable'])}',
            ),
            _Line(
              'Descartados por reglas',
              '${_asInt(space['rejected_physical'])}',
            ),
            _Line(
              'Paso de fraccion',
              fmtNumber(_asDouble(space['fraction_step']), 4),
            ),
            const Divider(height: 24),
            _Line('Rankeados ML', '${_asInt(screening['n_ranked'])}'),
            _Line('Elegibles', '${_asInt(screening['n_eligible'])}'),
            _Line('Pareto guardado', '${_asInt(screening['n_frontier'])}'),
            _Line('MLFF evaluados', '${_asInt(screening['n_mlff'])}'),
            const Divider(height: 24),
            _Line('Ronda preparada', '${_asInt(prepared['round_id'])}'),
            _Line('Seleccionados', '${_asInt(prepared['n_selected'])}'),
            _Line('Jobs preparados', '${_asInt(prepared['n_prepared'])}'),
            if (data.paths['dft_runs_dir'] != null)
              _Line('Runs DFT', data.paths['dft_runs_dir']!),
            if (data.paths['frontier'] != null)
              _Line('CSV Pareto', data.paths['frontier']!),
          ],
        ),
      ),
    );
  }
}

class _CandidateTableCard extends StatelessWidget {
  const _CandidateTableCard({
    required this.title,
    required this.subtitle,
    required this.items,
    this.compact = false,
  });

  final String title;
  final String subtitle;
  final List<DiscoveryCandidate> items;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final shown = items.take(compact ? 30 : 80).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                Text(
                  '${shown.length}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (shown.isEmpty)
              const SizedBox(
                height: 96,
                child: Center(child: Text('Sin candidatos en esta vista')),
              )
            else
              SizedBox(
                height: compact ? 330 : 420,
                child: Scrollbar(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SingleChildScrollView(
                      child: DataTable(
                        headingRowHeight: 38,
                        dataRowMinHeight: 38,
                        dataRowMaxHeight: 44,
                        columns: const [
                          DataColumn(label: Text('Fórmula')),
                          DataColumn(label: Text('Familia')),
                          DataColumn(label: Text('X')),
                          DataColumn(label: Text('Eg')),
                          DataColumn(label: Text('PV')),
                          DataColumn(label: Text('m*e')),
                          DataColumn(label: Text('m*h')),
                          DataColumn(label: Text('eps')),
                          DataColumn(label: Text('U')),
                          DataColumn(label: Text('Estado')),
                        ],
                        rows: [
                          for (final item in shown)
                            DataRow(
                              cells: [
                                DataCell(
                                  ConstrainedBox(
                                    constraints: const BoxConstraints(
                                      maxWidth: 180,
                                    ),
                                    child: Text(
                                      item.formula,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ),
                                DataCell(Text(item.bFamily)),
                                DataCell(Text(item.dominantHalide)),
                                DataCell(Text(fmtNumber(item.bandgapEv, 3))),
                                DataCell(Text(fmtNumber(item.pvScore, 3))),
                                DataCell(Text(fmtNumber(item.electronMass, 3))),
                                DataCell(Text(fmtNumber(item.holeMass, 3))),
                                DataCell(Text(fmtNumber(item.epsInf, 2))),
                                DataCell(
                                  Text(fmtNumber(item.uncertaintyScore, 3)),
                                ),
                                DataCell(Text(_statusLabel(item.status))),
                              ],
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ConfigTextField extends StatelessWidget {
  const _ConfigTextField({
    required this.label,
    required this.controller,
    required this.enabled,
    this.width = 150,
    this.numeric = false,
  });

  final String label;
  final TextEditingController controller;
  final bool enabled;
  final double width;
  final bool numeric;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: TextField(
        controller: controller,
        enabled: enabled,
        keyboardType: numeric
            ? const TextInputType.numberWithOptions(decimal: true)
            : TextInputType.text,
        decoration: InputDecoration(
          labelText: label,
          isDense: true,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }
}

class _MiniMetric extends StatelessWidget {
  const _MiniMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$label ',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        Text(
          value,
          style: Theme.of(context).textTheme.titleSmall,
        ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    required this.subvalue,
  });

  final String label;
  final String value;
  final String subvalue;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 176,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 4),
          Text(value, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 2),
          Text(
            subvalue,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.active});

  final String label;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final color = active ? Colors.greenAccent : Theme.of(context).dividerColor;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label, style: Theme.of(context).textTheme.bodySmall),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 145,
            child: Text(label, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(
            child: SelectableText(
              value,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

String _statusLabel(String status) {
  return switch (status) {
    'not_initialized' => 'sin iniciar',
    'initialized' => 'inicializado',
    'idle' => 'listo',
    'screening' => 'cribando ML',
    'dft_selected' => 'DFT seleccionado',
    'dft_prepared' => 'DFT preparado',
    'dft_running' => 'DFT corriendo',
    'paused' => 'pausado',
    'complete' => 'completo',
    'failed' => 'fallido',
    'viable_ml' => 'viable ML',
    'discarded' => 'descartado',
    _ => status,
  };
}

int _asInt(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse('$value') ?? 0;
}

double? _asDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse('$value');
}

List<String> _parseSpecies(String value) {
  return value
      .split(RegExp(r'[,;\s]+'))
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toSet()
      .toList();
}

double _parseDouble(String value) {
  final parsed = double.tryParse(value.trim().replaceAll(',', '.'));
  if (parsed == null) {
    throw FormatException('Número inválido: $value');
  }
  return parsed;
}

int _parseInt(String value) {
  final parsed = int.tryParse(value.trim());
  if (parsed == null) {
    throw FormatException('Entero inválido: $value');
  }
  return parsed;
}

String _modeLabel(String mode) {
  return switch (mode) {
    'pure' => 'Puros',
    'A_mixed' => 'A mixto',
    'B_mixed' => 'B mixto',
    'X_mixed' => 'X mixto',
    'multi_mixed' => 'Multi-mixto',
    _ => mode,
  };
}

String _modeCountsText(Map<String, int> counts) {
  final parts = [
    for (final entry in counts.entries)
      '${_modeLabel(entry.key)} ${entry.value}',
  ];
  return parts.join(' · ');
}
