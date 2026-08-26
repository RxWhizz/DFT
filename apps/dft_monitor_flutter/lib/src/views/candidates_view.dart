import 'dart:math' as math;

import '../exportar.dart';
import '../widgets/chart_kit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';
import '../widgets/status_chip.dart';

class CandidatesView extends ConsumerStatefulWidget {
  const CandidatesView({super.key});

  @override
  ConsumerState<CandidatesView> createState() => _CandidatesViewState();
}

class _CandidatesViewState extends ConsumerState<CandidatesView> {
  String _query = '';
  String _mode = '';
  String _halide = '';

  @override
  Widget build(BuildContext context) {
    final candidates = ref.watch(candidatesProvider(CandidatesQuery(
      q: _query,
      generationMode: _mode,
      halide: _halide,
    )));

    return AsyncPanel(
      value: candidates,
      builder: (data) {
        final points = data.items
            .where((item) => item.toleranceT != null && item.octFactor != null)
            .toList();
        final inside = points
            .where((item) =>
                item.toleranceT! >= data.goldschmidt.min &&
                item.toleranceT! <= data.goldschmidt.max &&
                item.octFactor! >= data.octahedral.min &&
                item.octFactor! <= data.octahedral.max)
            .length;
        final withDft = data.items.where((item) => item.hasDft).length;
        final converged =
            data.items.where((item) => item.dftStatus == 'converged').length;

        return Column(
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 280,
                  child: TextField(
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      hintText: 'Formula',
                    ),
                    onChanged: (value) => setState(() => _query = value),
                  ),
                ),
                _Select(
                  value: _mode,
                  hint: 'Modo',
                  options: data.facets['generation_mode'] ?? const [],
                  onChanged: (value) => setState(() => _mode = value),
                ),
                _Select(
                  value: _halide,
                  hint: 'Haluro',
                  options: data.facets['dominant_halide'] ?? const [],
                  onChanged: (value) => setState(() => _halide = value),
                ),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: Text(
                    data.source,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.end,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                _Metric(label: 'Candidatos', value: '${data.total}'),
                const SizedBox(width: 8),
                _Metric(label: 'Dentro', value: '$inside'),
                const SizedBox(width: 8),
                _Metric(label: 'Con DFT', value: '$withDft'),
                const SizedBox(width: 8),
                _Metric(label: 'Convergidos', value: '$converged'),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final plotWidth = (constraints.maxWidth * 0.36)
                      .clamp(430.0, 680.0)
                      .toDouble();
                  return Row(
                    children: [
                      SizedBox(
                        width: plotWidth,
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Mapa de estabilidad de Goldschmidt',
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleMedium),
                                const SizedBox(height: 8),
                                Expanded(
                                  child: _CandidateScatter(
                                    candidates: points,
                                    goldschmidt: data.goldschmidt,
                                    octahedral: data.octahedral,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Card(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Padding(
                                padding: const EdgeInsets.fromLTRB(12, 8, 8, 0),
                                child: Row(
                                  children: [
                                    Text('${data.items.length} candidatos',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall),
                                    const Spacer(),
                                    TextButton.icon(
                                      // Se exporta lo filtrado, no las 300 que
                                      // se pintan: la tabla recorta por
                                      // rendimiento, el archivo no debe.
                                      onPressed: () => guardarCsv(
                                        context,
                                        cabeceras: const [
                                          'formula', 'pv_score', 'eg_pred_ev',
                                          'eg_dft_ev', 'tolerance_t',
                                          'oct_factor', 'generation_mode',
                                          'b_family', 'batch', 'dft_status',
                                        ],
                                        filas: [
                                          for (final c in data.items)
                                            [
                                              c.formula,
                                              c.pvScore,
                                              c.egPred,
                                              c.egDft,
                                              c.toleranceT,
                                              c.octFactor,
                                              c.generationMode,
                                              c.bFamily,
                                              c.batch,
                                              c.dftStatus,
                                            ],
                                        ],
                                        nombre: 'candidatos',
                                      ),
                                      icon: const Icon(Icons.table_view_outlined,
                                          size: 18),
                                      label: const Text('Exportar CSV'),
                                    ),
                                  ],
                                ),
                              ),
                              Expanded(
                                child: _CandidateTable(
                                    items: data.items.take(300).toList()),
                              ),
                            ],
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
      },
    );
  }
}

class _Select extends StatelessWidget {
  const _Select({
    required this.value,
    required this.hint,
    required this.options,
    required this.onChanged,
  });

  final String value;
  final String hint;
  final List<String> options;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 170,
      child: DropdownButtonFormField<String>(
        initialValue: value.isEmpty ? null : value,
        decoration: InputDecoration(labelText: hint),
        items: [
          DropdownMenuItem(value: '', child: Text(hint)),
          for (final option in options)
            DropdownMenuItem(value: option, child: Text(option)),
        ],
        onChanged: (value) => onChanged(value ?? ''),
      ),
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
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelSmall),
              const SizedBox(height: 4),
              Text(value, style: Theme.of(context).textTheme.titleLarge),
            ],
          ),
        ),
      ),
    );
  }
}

class _CandidateTable extends StatelessWidget {
  const _CandidateTable({required this.items});

  final List<Candidate> items;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Fórmula')),
            DataColumn(label: Text('Score PV')),
            DataColumn(label: Text('Eg pred (eV)')),
            DataColumn(label: Text('Eg DFT (eV)')),
            DataColumn(label: Text('t')),
            DataColumn(label: Text('oct')),
            DataColumn(label: Text('Lote')),
            DataColumn(label: Text('DFT')),
          ],
          rows: [
            for (final item in items)
              DataRow(cells: [
                DataCell(Text(fmtFormula(item.formula))),
                DataCell(Text(fmtNumber(item.pvScore ?? item.score, 3))),
                DataCell(Text(fmtNumber(item.egPred, 3))),
                DataCell(Text(fmtNumber(item.egDft, 3))),
                DataCell(Text(fmtNumber(item.toleranceT, 3))),
                DataCell(Text(fmtNumber(item.octFactor, 3))),
                DataCell(Text(item.batch ?? item.generationMode ?? '-')),
                DataCell(item.dftStatus == null
                    ? const Text('-')
                    : StatusChip(item.dftStatus!)),
              ]),
          ],
        ),
      ),
    );
  }
}

class _CandidateScatter extends StatelessWidget {
  const _CandidateScatter({
    required this.candidates,
    required this.goldschmidt,
    required this.octahedral,
  });

  final List<Candidate> candidates;
  final RangeFilter goldschmidt;
  final RangeFilter octahedral;

  @override
  Widget build(BuildContext context) {
    if (candidates.isEmpty) return const Center(child: Text('Sin puntos'));
    final paleta = VizPalette.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: CustomPaint(
            painter: _ScatterPainter(
              candidates: candidates,
              goldschmidt: goldschmidt,
              octahedral: octahedral,
              paleta: paleta,
            ),
            child: const SizedBox.expand(),
          ),
        ),
        const SizedBox(height: 8),
        Leyenda([
          ItemLeyenda('Candidato', paleta.serie1),
          ItemLeyenda('Área de viabilidad', paleta.valido, relleno: false),
        ]),
      ],
    );
  }
}

class _ScatterPainter extends CustomPainter {
  const _ScatterPainter({
    required this.candidates,
    required this.goldschmidt,
    required this.octahedral,
    required this.paleta,
  });

  final List<Candidate> candidates;
  final RangeFilter goldschmidt;
  final RangeFilter octahedral;
  final VizPalette paleta;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Ejes.areaDe(size);
    final xs = candidates.map((c) => c.toleranceT!).toList();
    final ys = candidates.map((c) => c.octFactor!).toList();

    final ejes = Ejes(
      rect: rect,
      minX: math.min(xs.reduce(math.min), goldschmidt.min) - 0.04,
      maxX: math.max(xs.reduce(math.max), goldschmidt.max) + 0.04,
      minY: math.min(ys.reduce(math.min), octahedral.min) - 0.04,
      maxY: math.max(ys.reduce(math.max), octahedral.max) + 0.04,
      paleta: paleta,
    );

    // La banda va debajo de los puntos: sombrearlos los ocultaría.
    canvas.drawRect(
      Rect.fromLTRB(
        ejes.x(goldschmidt.min),
        ejes.y(octahedral.max),
        ejes.x(goldschmidt.max),
        ejes.y(octahedral.min),
      ),
      Paint()..color = paleta.valido.withValues(alpha: 0.10),
    );
    canvas.drawRect(
      Rect.fromLTRB(
        ejes.x(goldschmidt.min),
        ejes.y(octahedral.max),
        ejes.x(goldschmidt.max),
        ejes.y(octahedral.min),
      ),
      Paint()
        ..color = paleta.valido.withValues(alpha: 0.55)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );

    ejes.dibujar(
      canvas,
      tituloX: 'Factor de tolerancia t (Goldschmidt)',
      tituloY: 'Factor octaédrico μ',
    );

    // El score se reparte en un rango estrecho, así que un radio proporcional
    // al valor crudo no se distinguía: se escala contra el máximo observado.
    final scores = candidates.map((c) => (c.score ?? 0).abs()).toList();
    final maxScore = scores.isEmpty ? 1.0 : math.max(0.001, scores.reduce(math.max));

    final punto = Paint()..color = paleta.serie1.withValues(alpha: 0.72);
    for (final c in candidates.take(2000)) {
      final rel = (c.score ?? 0).abs() / maxScore;
      canvas.drawCircle(
        Offset(ejes.x(c.toleranceT!), ejes.y(c.octFactor!)),
        2.6 + 3.4 * rel,
        punto,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ScatterPainter oldDelegate) {
    return oldDelegate.candidates != candidates ||
        oldDelegate.goldschmidt != goldschmidt ||
        oldDelegate.octahedral != octahedral ||
        oldDelegate.paleta.oscuro != paleta.oscuro;
  }
}
