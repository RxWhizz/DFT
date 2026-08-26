import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';
import '../widgets/confirm_action.dart';
import '../widgets/status_chip.dart';

class JobsView extends ConsumerStatefulWidget {
  const JobsView({super.key});

  @override
  ConsumerState<JobsView> createState() => _JobsViewState();
}

class _JobsViewState extends ConsumerState<JobsView> {
  String? _selectedJobId;
  String _query = '';
  String? _status;

  @override
  Widget build(BuildContext context) {
    final jobs = ref.watch(jobsProvider(JobsQuery(q: _query, status: _status)));

    return LayoutBuilder(
      builder: (context, constraints) {
        final listWidth =
            (constraints.maxWidth * 0.34).clamp(460.0, 760.0).toDouble();
        return Row(
          children: [
            SizedBox(
              width: listWidth,
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          decoration: const InputDecoration(
                              prefixIcon: Icon(Icons.search),
                              hintText: 'Fórmula o id del trabajo'),
                          onChanged: (value) => setState(() => _query = value),
                        ),
                      ),
                      const SizedBox(width: 8),
                      DropdownButton<String?>(
                        value: _status,
                        hint: const Text('Estado'),
                        items: const [
                          DropdownMenuItem<String?>(
                              value: null, child: Text('Todos')),
                          DropdownMenuItem(
                              value: 'running', child: Text('calculando')),
                          DropdownMenuItem(
                              value: 'pending', child: Text('en cola')),
                          DropdownMenuItem(
                              value: 'converged', child: Text('convergido')),
                          DropdownMenuItem(
                              value: 'failed', child: Text('fallido')),
                          DropdownMenuItem(
                              value: 'stalled,oscillating',
                              child: Text('estancado')),
                        ],
                        onChanged: (value) => setState(() => _status = value),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: Card(
                      child: AsyncPanel(
                        value: jobs,
                        builder: (page) {
                          if (page.items.isEmpty) {
                            return const Center(child: Text('Sin jobs'));
                          }
                          final selectedExists = page.items
                              .any((job) => job.jobId == _selectedJobId);
                          if (!selectedExists) {
                            WidgetsBinding.instance.addPostFrameCallback((_) {
                              if (mounted) {
                                setState(() =>
                                    _selectedJobId = page.items.first.jobId);
                              }
                            });
                          }
                          return ListView.separated(
                            itemCount: page.items.length,
                            separatorBuilder: (_, __) =>
                                const Divider(height: 1),
                            itemBuilder: (context, index) {
                              final job = page.items[index];
                              final selected = job.jobId == _selectedJobId;
                              return ListTile(
                                selected: selected,
                                selectedTileColor: Theme.of(context)
                                    .colorScheme
                                    .primary
                                    .withValues(alpha: 0.12),
                                title: Text(fmtFormula(job.formula),
                                    overflow: TextOverflow.ellipsis),
                                subtitle: Text(job.jobId,
                                    overflow: TextOverflow.ellipsis),
                                trailing: StatusChip(job.status),
                                onTap: () =>
                                    setState(() => _selectedJobId = job.jobId),
                              );
                            },
                          );
                        },
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: _selectedJobId == null
                  ? const Card(child: Center(child: Text('Selecciona un trabajo')))
                  : _JobDetail(jobId: _selectedJobId!),
            ),
          ],
        );
      },
    );
  }
}

class _JobDetail extends ConsumerStatefulWidget {
  const _JobDetail({required this.jobId});

  final String jobId;

  @override
  ConsumerState<_JobDetail> createState() => _JobDetailState();
}

class _JobDetailState extends ConsumerState<_JobDetail> {
  String? _notice;
  bool _diagnosing = false;

  @override
  Widget build(BuildContext context) {
    final job = ref.watch(jobProvider(widget.jobId));
    final log = ref.watch(jobLogProvider(JobLogPeticion(jobId: widget.jobId)));
    final traces = ref.watch(jobTracesProvider(widget.jobId));
    final metadata = ref.watch(jobMetadataProvider(widget.jobId));
    final actions = ref.watch(jobActionsProvider);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AsyncPanel(
              value: job,
              builder: (data) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(fmtFormula(data.formula),
                                style: Theme.of(context).textTheme.titleLarge),
                            const SizedBox(height: 4),
                            SelectableText(data.jobId,
                                style: Theme.of(context).textTheme.bodySmall),
                          ],
                        ),
                      ),
                      const SizedBox(width: 12),
                      StatusChip(data.status),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      FilledButton.icon(
                        onPressed:
                            _diagnosing ? null : () => _diagnose(data.jobId),
                        icon: const Icon(Icons.manage_search_outlined),
                        label: Text(_diagnosing ? '...' : 'Diagnosticar'),
                      ),
                      OutlinedButton(
                        onPressed: () async {
                          if (await confirmAction(
                            context,
                            title: 'Detener trabajo',
                            message:
                                'Se detendran los procesos asociados a ${widget.jobId}.',
                            confirmLabel: 'Detener',
                          )) {
                            await actions.kill(widget.jobId);
                            ref.invalidate(jobProvider(widget.jobId));
                            ref.invalidate(jobsProvider);
                            setState(() => _notice = 'Job detenido.');
                          }
                        },
                        child: const Text('Detener'),
                      ),
                      OutlinedButton(
                        onPressed: () async {
                          if (await confirmAction(
                            context,
                            title: 'Reintentar trabajo',
                            message: 'El trabajo volverá a la cola de pendientes.',
                            confirmLabel: 'Reintentar',
                          )) {
                            await actions.retry(widget.jobId);
                            ref.invalidate(jobProvider(widget.jobId));
                            ref.invalidate(jobsProvider);
                            setState(() => _notice = 'Job devuelto a cola.');
                          }
                        },
                        child: const Text('Reintentar'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            if (_notice != null) ...[
              const SizedBox(height: 8),
              Text(_notice!, style: Theme.of(context).textTheme.bodySmall),
            ],
            const SizedBox(height: 12),
            Expanded(
              child: DefaultTabController(
                length: 4,
                child: Column(
                  children: [
                    const TabBar(tabs: [
                      Tab(text: 'Trazas'),
                      Tab(text: 'Frames'),
                      Tab(text: 'Log'),
                      Tab(text: 'Ficha'),
                    ]),
                    Expanded(
                      child: TabBarView(
                        children: [
                          _TracesPanel(value: traces),
                          _FramesPanel(value: traces),
                          _LogPanel(value: log),
                          _FichaPanel(value: metadata),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _diagnose(String jobId) async {
    setState(() {
      _diagnosing = true;
      _notice = null;
    });
    try {
      final response = await ref.read(agentActionsProvider).chat(
            message: 'Diagnostica este trabajo y sugiere acciones seguras.',
            history: const [],
            structured: true,
            jobId: jobId,
          );
      final summary = response.structured?['summary'];
      setState(() => _notice = '${summary ?? response.message}');
    } catch (error) {
      setState(() => _notice = '$error');
    } finally {
      if (mounted) setState(() => _diagnosing = false);
    }
  }
}

class _TracesPanel extends StatelessWidget {
  const _TracesPanel({required this.value});

  final AsyncValue<Map<String, dynamic>> value;

  @override
  Widget build(BuildContext context) {
    return AsyncPanel(
      value: value,
      builder: (data) {
        final labels = (data['labels'] as List? ?? const []).cast<Object?>();
        if (labels.isEmpty) {
          return const Center(child: Text('Sin iteraciones SCF'));
        }
        return SingleChildScrollView(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              for (final raw in labels)
                _TraceCard(data: Map<String, dynamic>.from(raw as Map)),
            ],
          ),
        );
      },
    );
  }
}

class _TraceCard extends StatelessWidget {
  const _TraceCard({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final points = (data['points'] as List? ?? const []).cast<Object?>();
    final last =
        points.isEmpty ? null : Map<String, dynamic>.from(points.last as Map);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                    child: Text('${data['label'] ?? '-'}',
                        style: Theme.of(context).textTheme.titleSmall)),
                Text('${data['n_iters'] ?? points.length} iter'),
                if (data['rate_s_per_iter'] != null) ...[
                  const SizedBox(width: 12),
                  Text(
                      '${fmtNumber(data['rate_s_per_iter'] as num?, 0)} s/iter'),
                ],
              ],
            ),
            const SizedBox(height: 8),
            if (last != null)
              Wrap(
                spacing: 16,
                children: [
                  Text('iter ${last['iter'] ?? '-'}'),
                  Text('E ${fmtNumber(last['energy'] as num?, 6)}'),
                  Text('dens ${fmtNumber(last['dens'] as num?, 3)}'),
                  Text('eigst ${fmtNumber(last['eigst'] as num?, 3)}'),
                ],
              ),
            const SizedBox(height: 8),
            SizedBox(
              height: 150,
              child: _EnergySpark(points: points),
            ),
          ],
        ),
      ),
    );
  }
}

class _EnergySpark extends StatelessWidget {
  const _EnergySpark({required this.points});

  final List<Object?> points;

  @override
  Widget build(BuildContext context) {
    final values = [
      for (final point in points)
        if ((point as Map)['energy'] is num)
          ((point)['energy'] as num).toDouble(),
    ];
    if (values.length < 2) return const Center(child: Text('Sin serie'));
    return CustomPaint(
      painter: _LinePainter(
          values: values, color: Theme.of(context).colorScheme.primary),
      child: const SizedBox.expand(),
    );
  }
}

class _LinePainter extends CustomPainter {
  const _LinePainter({required this.values, required this.color});

  final List<double> values;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final min = values.reduce((a, b) => a < b ? a : b);
    final max = values.reduce((a, b) => a > b ? a : b);
    final span = max == min ? 1.0 : max - min;
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = size.width * i / (values.length - 1);
      final y = size.height - ((values[i] - min) / span) * size.height;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    final grid = Paint()
      ..color = const Color(0xff263244)
      ..strokeWidth = 1;
    canvas.drawLine(
        Offset(0, size.height), Offset(size.width, size.height), grid);
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
  }

  @override
  bool shouldRepaint(covariant _LinePainter oldDelegate) =>
      oldDelegate.values != values || oldDelegate.color != color;
}

class _FramesPanel extends StatelessWidget {
  const _FramesPanel({required this.value});

  final AsyncValue<Map<String, dynamic>> value;

  @override
  Widget build(BuildContext context) {
    return AsyncPanel(
      value: value,
      builder: (data) {
        final frames = (data['frames'] as List? ?? const []).cast<Object?>();
        if (frames.isEmpty) {
          return const Center(child: Text('Sin frames etiquetados'));
        }
        return SingleChildScrollView(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: const [
                DataColumn(label: Text('Configuración')),
                DataColumn(label: Text('Estado')),
                DataColumn(label: Text('Energía')),
                DataColumn(label: Text('eV/at')),
                DataColumn(label: Text('fmax')),
                DataColumn(label: Text('Tiempo')),
              ],
              rows: [
                for (final raw in frames)
                  _frameRow(Map<String, dynamic>.from(raw as Map)),
              ],
            ),
          ),
        );
      },
    );
  }

  DataRow _frameRow(Map<String, dynamic> frame) {
    return DataRow(cells: [
      DataCell(
          Text('${frame['label'] ?? '-'}/${frame['config_index'] ?? '-'}')),
      DataCell(Text('${frame['status'] ?? '-'}')),
      DataCell(Text(fmtNumber(frame['energy_ev'] as num?, 4))),
      DataCell(Text(fmtNumber(frame['energy_per_atom_ev'] as num?, 4))),
      DataCell(Text(fmtNumber(frame['forces_max_eva'] as num?, 4))),
      DataCell(Text(fmtNumber(frame['elapsed_s'] as num?, 1))),
    ]);
  }
}

class _LogPanel extends StatelessWidget {
  const _LogPanel({required this.value});

  final AsyncValue<LogJob> value;

  @override
  Widget build(BuildContext context) {
    return AsyncPanel(
      value: value,
      builder: (data) {
        final lines = data.lineas;
        if (lines.isEmpty) return const Center(child: Text('Sin log'));
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                '${data.etiqueta ?? '-'} · ${lines.length} de ${data.total} lineas',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(12),
                child: SelectableText(
                  lines.join('\n'),
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _FichaPanel extends StatelessWidget {
  const _FichaPanel({required this.value});

  final AsyncValue<Map<String, dynamic>> value;

  @override
  Widget build(BuildContext context) {
    return AsyncPanel(
      value: value,
      builder: (data) {
        final metadata =
            Map<String, dynamic>.from(data['metadata'] as Map? ?? {});
        final status = Map<String, dynamic>.from(data['status'] as Map? ?? {});
        final artifacts = [
          for (final item in (data['artifacts'] as List? ?? const [])) '$item'
        ];
        final destacado = <String, Object?>{
          'Formula': metadata['formula'],
          'Modo': metadata['generation_mode'],
          'Atomos': metadata['n_atoms'],
          'Goldschmidt': metadata['tolerance_t'],
          'Octaedrico': metadata['oct_factor'],
          'Estado': status['status'],
        }..removeWhere((_, value) => value == null);
        return SingleChildScrollView(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 16,
                runSpacing: 8,
                children: [
                  for (final entry in destacado.entries)
                    Chip(label: Text('${entry.key}: ${entry.value}')),
                ],
              ),
              const SizedBox(height: 12),
              Text('metadata.json',
                  style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 6),
              SelectableText(
                const JsonEncoder.withIndent('  ').convert(metadata),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
              const SizedBox(height: 12),
              Text('Artefactos (${artifacts.length})',
                  style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 6),
              SelectableText(artifacts.join('\n'),
                  style:
                      const TextStyle(fontFamily: 'monospace', fontSize: 12)),
            ],
          ),
        );
      },
    );
  }
}
