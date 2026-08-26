import '../api/errors.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';
import '../widgets/confirm_action.dart';

class ScreeningView extends ConsumerStatefulWidget {
  const ScreeningView({super.key});

  @override
  ConsumerState<ScreeningView> createState() => _ScreeningViewState();
}

class _ScreeningViewState extends ConsumerState<ScreeningView> {
  int _seed = DateTime.now().millisecondsSinceEpoch % 1000000;
  int _batches = 1;
  int _candidates = 200;
  String? _activeRunId;
  bool _runningMutation = false;

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(screeningConfigProvider);
    final runs = ref.watch(screeningRunsProvider);
    final runsValue = runs.asData?.value;
    final activeId = _activeRunId ??
        (runsValue != null && runsValue.isNotEmpty
            ? runsValue.first.runId
            : null);
    final activeRun =
        activeId == null ? null : ref.watch(screeningRunProvider(activeId));
    final activeRunValue = activeRun?.asData?.value;
    final canStartDft = activeRunValue != null &&
        activeRunValue.status == 'done' &&
        activeRunValue.nSelected > 0 &&
        (activeRunValue.dftPrepared ?? 0) == 0;
    final canLaunchPrepared = activeRunValue != null &&
        activeRunValue.status == 'done' &&
        (activeRunValue.dftPrepared ?? 0) > 0;

    return Column(
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.end,
              children: [
                _NumberBox(
                    label: 'Semilla',
                    value: _seed,
                    min: 0,
                    max: 999999999,
                    onChanged: (v) => setState(() => _seed = v)),
                _NumberBox(
                    label: 'Lotes',
                    value: _batches,
                    min: 1,
                    max: 50,
                    onChanged: (v) => setState(() => _batches = v)),
                _NumberBox(
                    label: 'Candidatos/lote',
                    value: _candidates,
                    min: 1,
                    max: _maxCandidates,
                    onChanged: (v) => setState(() => _candidates = v)),
                FilledButton.icon(
                  onPressed:
                      _runningMutation ? null : () => _runScreening(context),
                  icon: const Icon(Icons.play_arrow),
                  label: Text(_runningMutation ? '...' : 'Ejecutar'),
                ),
                if (canStartDft)
                  OutlinedButton.icon(
                    onPressed: _runningMutation
                        ? null
                        : () => _startDft(context, activeRunValue.runId),
                    icon: const Icon(Icons.science_outlined),
                    label: const Text('Empezar DFT'),
                  ),
                if (canLaunchPrepared)
                  OutlinedButton.icon(
                    onPressed: _runningMutation
                        ? null
                        : () => _launchPreparedBatch(context,
                            activeRunValue.batchId, activeRunValue.runId),
                    icon: const Icon(Icons.rocket_launch_outlined),
                    label: const Text('Lanzar'),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final sideWidth =
                  (constraints.maxWidth * 0.30).clamp(420.0, 620.0).toDouble();
              return Row(
                children: [
                  SizedBox(
                    width: sideWidth,
                    child: Column(
                      children: [
                        Expanded(
                          child: Card(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: activeRun == null
                                  ? const Center(
                                      child: Text('Sin ejecucion activa'))
                                  : AsyncPanel(
                                      value: activeRun,
                                      builder: (run) => _Funnel(run: run)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 220,
                          child: Card(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: AsyncPanel(
                                  value: config,
                                  builder: (cfg) => _Gates(config: cfg)),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: activeRun == null
                            ? const Center(
                                child: Text(
                                    'Ejecuta un cribado para ver el ranking'))
                            : AsyncPanel(
                                value: activeRun,
                                builder: (run) => _Ranking(run: run)),
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }

  int get _maxCandidates =>
      (5000 / _batches.clamp(1, 50)).floor().clamp(1, 5000);

  Future<void> _runScreening(BuildContext context) async {
    setState(() => _runningMutation = true);
    try {
      final action = ref.read(screeningActionsProvider);
      final run = await action.run(
        randomSeed: _seed,
        nBatches: _batches,
        nCandidates: _candidates.clamp(1, _maxCandidates),
      );
      setState(() => _activeRunId = run.runId);
      ref.invalidate(screeningRunsProvider);
      ref.invalidate(screeningRunProvider(run.runId));
    } catch (error) {
      if (context.mounted) _showError(context, error);
    } finally {
      if (mounted) setState(() => _runningMutation = false);
    }
  }

  Future<void> _startDft(BuildContext context, String runId) async {
    final startRunner = await _confirmStartDft(context);
    if (startRunner == null) {
      return;
    }
    setState(() => _runningMutation = true);
    try {
      final result = await ref.read(screeningActionsProvider).startDft(
            runId,
            startRunner: startRunner,
          );
      ref.invalidate(screeningRunProvider(runId));
      ref.invalidate(structuresProvider);
      ref.invalidate(jobsProvider);
      if (context.mounted) {
        final text = result.runnerLaunched
            ? 'DFT preparado y runner iniciado para batch ${result.batchId}.'
            : 'DFT preparado: ${result.nPrepared} jobs en batch ${result.batchId}.';
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(text)));
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    } finally {
      if (mounted) setState(() => _runningMutation = false);
    }
  }

  Future<void> _launchPreparedBatch(
      BuildContext context, int batchId, String runId) async {
    if (!await confirmAction(
      context,
      title: 'Lanzar lote',
      message: 'Se arrancará el runner local para el lote $batchId.',
      confirmLabel: 'Lanzar',
    )) {
      return;
    }
    setState(() => _runningMutation = true);
    try {
      await ref.read(jobActionsProvider).startBatch(batchId);
      ref.invalidate(screeningRunProvider(runId));
      ref.invalidate(jobsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Runner iniciado para el lote $batchId.')),
        );
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    } finally {
      if (mounted) setState(() => _runningMutation = false);
    }
  }

  Future<bool?> _confirmStartDft(BuildContext context) {
    var startRunner = false;
    return showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Empezar DFT'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                  'Se prepararan los candidatos seleccionados como jobs DFT.'),
              const SizedBox(height: 8),
              CheckboxListTile(
                value: startRunner,
                title: const Text('Arrancar runner ahora'),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: (value) =>
                    setDialogState(() => startRunner = value ?? false),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancelar')),
            FilledButton(
              onPressed: () => Navigator.pop(context, startRunner),
              child: const Text('Preparar'),
            ),
          ],
        ),
      ),
    );
  }

  void _showError(BuildContext context, Object error) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
  }
}

class _NumberBox extends StatelessWidget {
  const _NumberBox({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
  });

  final String label;
  final int value;
  final int min;
  final int max;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 140,
      child: TextFormField(
        initialValue: '$value',
        decoration: InputDecoration(labelText: label),
        keyboardType: TextInputType.number,
        onChanged: (text) {
          final next = int.tryParse(text) ?? value;
          onChanged(next.clamp(min, max));
        },
      ),
    );
  }
}

class _Funnel extends StatelessWidget {
  const _Funnel({required this.run});

  final ScreeningRun run;

  @override
  Widget build(BuildContext context) {
    if (run.error != null) {
      return Text(run.error!,
          style: TextStyle(color: Theme.of(context).colorScheme.error));
    }
    if (run.tiers.isEmpty) {
      return Center(
          child: Text(run.status == 'running' ? run.stage : 'Sin tiers'));
    }
    final total = run.tiers.first.nIn == 0 ? 1 : run.tiers.first.nIn;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Cascada', style: Theme.of(context).textTheme.titleMedium),
        Text(
            '${run.nRequested} pedidos · ${run.nBatches} lotes · semilla ${run.randomSeed}'),
        const SizedBox(height: 12),
        for (final tier in run.tiers)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('TIER ${tier.tier}',
                        style: Theme.of(context).textTheme.labelSmall),
                    const SizedBox(width: 8),
                    Text(tier.name),
                    const Spacer(),
                    Text('${tier.nOut}'),
                  ],
                ),
                const SizedBox(height: 4),
                LinearProgressIndicator(value: tier.nOut / total),
                const SizedBox(height: 2),
                Text('${tier.nIn} entran · ${tier.nDropped} fuera',
                    style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
      ],
    );
  }
}

class _Gates extends StatelessWidget {
  const _Gates({required this.config});

  final ScreeningConfig config;

  @override
  Widget build(BuildContext context) {
    if (!config.available) {
      return Text(config.reason ?? 'Cribado no disponible');
    }
    final gates = config.gates;
    String range(String key, String min, String max) {
      final data = Map<String, dynamic>.from(gates[key] as Map? ?? {});
      return '${data[min]} - ${data[max]}';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Cotas', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        _GateLine('Goldschmidt t', range('goldschmidt', 'min', 'max')),
        _GateLine('Factor octaedrico', range('octahedral', 'min', 'max')),
        _GateLine('Volumen A3', range('volume_A3', 'min', 'max')),
        _GateLine('E_form max', '${gates['eform_max_eV_atom']} eV/at'),
      ],
    );
  }
}

class _GateLine extends StatelessWidget {
  const _GateLine(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [Expanded(child: Text(label)), Text(value)]),
    );
  }
}

class _Ranking extends StatelessWidget {
  const _Ranking({required this.run});

  final ScreeningRun run;

  @override
  Widget build(BuildContext context) {
    if (run.items.isEmpty) {
      return Center(
          child: Text(run.status == 'running' ? run.stage : 'Sin ranking'));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Ranking por total_score',
                style: Theme.of(context).textTheme.titleMedium),
            const Spacer(),
            Text(
                '${run.items.length} de ${run.nItemsTotal} · ${run.nSelected} irian a DFT'),
          ],
        ),
        const SizedBox(height: 8),
        Expanded(
          child: SingleChildScrollView(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columns: const [
                  DataColumn(label: Text('Fórmula')),
                  DataColumn(label: Text('Eg')),
                  DataColumn(label: Text('sigma')),
                  DataColumn(label: Text('PV')),
                  DataColumn(label: Text('E_form')),
                  DataColumn(label: Text('band')),
                  DataColumn(label: Text('stab')),
                  DataColumn(label: Text('ucb')),
                  DataColumn(label: Text('total')),
                ],
                rows: [
                  for (final row in run.items)
                    DataRow(cells: [
                      DataCell(Text(fmtFormula(row['formula'] as String?))),
                      DataCell(
                          Text(fmtNumber(row['Eg_surrogate_eV'] as num?, 3))),
                      DataCell(Text(fmtNumber(row['Eg_sigma_eV'] as num?, 3))),
                      DataCell(Text(row['in_pv_window'] == true ? 'si' : '-')),
                      DataCell(
                          Text(fmtNumber(row['Eform_eV_atom'] as num?, 3))),
                      DataCell(Text(fmtNumber(row['band_score'] as num?, 2))),
                      DataCell(Text(fmtNumber(row['stab_score'] as num?, 2))),
                      DataCell(Text(fmtNumber(row['ucb_bonus'] as num?, 2))),
                      DataCell(Text(fmtNumber(row['total_score'] as num?, 3))),
                    ]),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
