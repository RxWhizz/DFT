import '../widgets/bench_dialog.dart';
import '../api/errors.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';
import '../widgets/confirm_action.dart';
import '../widgets/status_chip.dart';

class BatchesView extends ConsumerWidget {
  const BatchesView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final batches = ref.watch(batchesProvider);

    return AsyncPanel(
      value: batches,
      builder: (items) {
        return RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(batchesProvider);
            ref.invalidate(summaryProvider);
            ref.invalidate(jobsProvider);
          },
          child: ListView.separated(
            itemCount: items.length + 1,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              if (index == 0) {
                return _Header(items: items);
              }
              final batch = items[index - 1];
              return _BatchRow(
                batch: batch,
                onStart: () => _startBatch(context, ref, batch),
              );
            },
          ),
        );
      },
    );
  }

  Future<void> _startBatch(
    BuildContext context,
    WidgetRef ref,
    BatchInfo batch,
  ) async {
    if (!await confirmAction(
      context,
      title: 'Lanzar lote',
      message: 'Se arrancará el runner local para el lote ${batch.batchId}.',
      confirmLabel: 'Lanzar',
    )) {
      return;
    }
    try {
      await ref.read(jobActionsProvider).startBatch(batch.batchId);
      ref.invalidate(batchesProvider);
      ref.invalidate(summaryProvider);
      ref.invalidate(jobsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('Runner iniciado para el lote ${batch.batchId}.')),
        );
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(mensajeDeError(error))),
        );
      }
    }
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.items});

  final List<BatchInfo> items;

  @override
  Widget build(BuildContext context) {
    final totalJobs = items.fold<int>(0, (sum, item) => sum + item.total);
    final pending = items.fold<int>(0, (sum, item) => sum + item.nPending);
    final running = items.where((item) => item.runnerLaunched).length;

    return Row(
      children: [
        _Metric(label: 'Lotes', value: '${items.length}'),
        const SizedBox(width: 8),
        _Metric(label: 'Jobs', value: '$totalJobs'),
        const SizedBox(width: 8),
        _Metric(label: 'Pendientes', value: '$pending'),
        const SizedBox(width: 8),
        _Metric(label: 'Runners', value: '$running'),
        const Spacer(),
        // Cuántos slots y núcleos poner es justo la decisión que se toma aquí,
        // así que el acceso a la calibración vive en esta pantalla.
        OutlinedButton.icon(
          onPressed: () => showBenchDialog(context),
          icon: const Icon(Icons.speed, size: 18),
          label: const Text('Calibrar rendimiento'),
        ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelSmall),
              const SizedBox(height: 6),
              Text(value, style: Theme.of(context).textTheme.titleLarge),
            ],
          ),
        ),
      ),
    );
  }
}

class _BatchRow extends StatelessWidget {
  const _BatchRow({
    required this.batch,
    required this.onStart,
  });

  final BatchInfo batch;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final title = 'batch_${batch.batchId.toString().padLeft(3, '0')}';
    final canStart = batch.nPending > 0;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 116,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 6),
                  if (batch.isCurrent) const StatusChip('actual'),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final entry in batch.counts.entries)
                        StatusChip('${entry.key}:${entry.value}'),
                      if (batch.counts.isEmpty) const StatusChip('vacio'),
                    ],
                  ),
                  const SizedBox(height: 10),
                  SelectableText(
                    batch.path,
                    maxLines: 1,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 160,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('${batch.total} trabajos'),
                  Text('${batch.nPending} pendientes',
                      style: Theme.of(context).textTheme.bodySmall),
                  Text('${fmtNumber(batch.ratePerHour, 1)} / h',
                      style: Theme.of(context).textTheme.bodySmall),
                  Text(_fmtEta(batch.etaSec),
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            const SizedBox(width: 12),
            OutlinedButton.icon(
              onPressed: canStart ? onStart : null,
              icon: const Icon(Icons.play_arrow),
              label: const Text('Lanzar'),
            ),
          ],
        ),
      ),
    );
  }

  String _fmtEta(double? seconds) {
    if (seconds == null) return 'ETA -';
    if (seconds < 60) return 'ETA ${seconds.toStringAsFixed(0)} s';
    if (seconds < 3600) return 'ETA ${(seconds / 60).toStringAsFixed(0)} min';
    return 'ETA ${(seconds / 3600).toStringAsFixed(1)} h';
  }
}
