
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';




class MlView extends ConsumerStatefulWidget {
  const MlView({super.key});

  @override
  ConsumerState<MlView> createState() => _MlViewState();
}

class _MlViewState extends ConsumerState<MlView> {

  @override
  Widget build(BuildContext context) {
    final models = ref.watch(modelsProvider);
    final top8 = ref.watch(top8Provider);
    final modelsValue = models.asData?.value;
    final unavailable = modelsValue?.surrogateStatus == 'error';

    return Column(
      children: [
        if (unavailable)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                modelsValue?.surrogateError ?? 'Surrogate no disponible',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ),
        if (unavailable) const SizedBox(height: 12),
        Expanded(
          child: Card(
            child: AsyncPanel(
              value: top8,
              builder: (data) => _Top8Table(rows: data.items),
            ),
          ),
        ),
        const SizedBox(height: 12),
        _ModelsStrip(value: models),
      ],
    );
  }

}

class _Top8Table extends StatelessWidget {
  const _Top8Table({required this.rows});

  final List<Top8Row> rows;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Material')),
            DataColumn(label: Text('Predictor')),
            DataColumn(label: Text('σ')),
            DataColumn(label: Text('DFT')),
            DataColumn(label: Text('Exp')),
            DataColumn(label: Text('|pred − exp|')),
            DataColumn(label: Text('PV')),
          ],
          rows: [
            for (final row in rows)
              DataRow(cells: [
                DataCell(Text(fmtFormula(row.material))),
                DataCell(Text(fmtNumber(row.egMl, 3))),
                DataCell(Text(fmtNumber(row.egMlStd, 3))),
                DataCell(Text(fmtNumber(row.egDft, 3))),
                DataCell(Text(fmtNumber(row.egExp, 2))),
                DataCell(Text(fmtNumber(
                  row.egMl != null && row.egExp != null
                      ? (row.egMl! - row.egExp!).abs()
                      : null,
                  3,
                ))),
                DataCell(Text(row.inPvWindow == null
                    ? '-'
                    : row.inPvWindow!
                        ? 'si'
                        : '-')),
              ]),
          ],
        ),
      ),
    );
  }
}

class _ModelsStrip extends StatelessWidget {
  const _ModelsStrip({required this.value});

  final AsyncValue<ModelsResponse> value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 164,
      child: AsyncPanel(
        value: value,
        builder: (data) => LayoutBuilder(
          builder: (context, constraints) {
            final canFillWidth =
                data.models.isNotEmpty && constraints.maxWidth >= 760;
            if (canFillWidth) {
              return Row(
                children: [
                  for (var index = 0; index < data.models.length; index++) ...[
                    Expanded(child: _ModelCard(model: data.models[index])),
                    if (index != data.models.length - 1)
                      const SizedBox(width: 8),
                  ],
                ],
              );
            }
            return ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: data.models.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, index) =>
                  _ModelCard(model: data.models[index], width: 260),
            );
          },
        ),
      ),
    );
  }
}

class _ModelCard extends StatelessWidget {
  const _ModelCard({required this.model, this.width});

  final ModelInfo model;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final cvRaw = model.metrics['cv'];
    final cv =
        cvRaw is Map ? Map<String, dynamic>.from(cvRaw) : <String, dynamic>{};
    return SizedBox(
      width: width,
      child: Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(model.name.replaceFirst('surrogate_', ''),
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              _Line('MAE CV', fmtNumber(cv['MAE_eV'] as num?, 3)),
              _Line('R2', fmtNumber(cv['R2'] as num?, 3)),
              _Line('muestras',
                  '${model.metrics['n_samples'] ?? cv['n_samples'] ?? '-'}'),
              _Line('pickle', model.hasPickle ? 'si' : 'no'),
            ],
          ),
        ),
      ),
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
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(
              child: Text(label, style: Theme.of(context).textTheme.bodySmall)),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.end,
            ),
          ),
        ],
      ),
    );
  }
}

