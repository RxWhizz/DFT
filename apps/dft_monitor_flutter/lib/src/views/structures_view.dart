import '../exportar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../structures/cif_viewer.dart';
import '../utils/format.dart';
import '../widgets/async_panel.dart';

// El orden importa: las fases de referencia y el top 8 son pocas y siempre
// tienen geometría válida, así que van arriba. Antes las noventa «recientes»
// las enterraban y había que bajar hasta el fondo para encontrarlas.
const _groups = <String, String>{
  'fases': 'Fases de referencia',
  'top8': 'Top 8',
  'jobs': 'Lote en curso',
  'recientes': 'Otras recientes',
};

class StructuresView extends ConsumerStatefulWidget {
  const StructuresView({super.key});

  @override
  ConsumerState<StructuresView> createState() => _StructuresViewState();
}

class _StructuresViewState extends ConsumerState<StructuresView> {
  String? _selectedId;
  final GlobalKey _claveFigura = GlobalKey();
  String _filter = '';
  String _style = 'ball-stick';
  int _supercell = 1;
  bool _showCell = true;

  @override
  Widget build(BuildContext context) {
    final structures = ref.watch(structuresProvider);
    final selectedContent = _selectedId == null
        ? null
        : ref.watch(structureContentProvider(_selectedId!));

    return LayoutBuilder(
      builder: (context, constraints) {
        final listWidth =
            (constraints.maxWidth * 0.23).clamp(320.0, 500.0).toDouble();
        return Row(
          children: [
            SizedBox(
              width: listWidth,
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    children: [
                      TextField(
                        decoration: const InputDecoration(
                          prefixIcon: Icon(Icons.search),
                          hintText: 'Filtrar',
                        ),
                        onChanged: (value) => setState(() => _filter = value),
                      ),
                      const SizedBox(height: 12),
                      Expanded(
                        child: AsyncPanel(
                          value: structures,
                          builder: (items) {
                            final filtered = items.where((item) {
                              final text = '${item.name} ${item.detail ?? ''}'
                                  .toLowerCase();
                              return _filter.isEmpty ||
                                  text.contains(_filter.toLowerCase());
                            }).toList();
                            if (_selectedId == null && filtered.isNotEmpty) {
                              WidgetsBinding.instance.addPostFrameCallback((_) {
                                if (mounted && _selectedId == null) {
                                  setState(
                                      () => _selectedId = filtered.first.id);
                                }
                              });
                            }
                            return ListView(
                              children: [
                                for (final entry in _groups.entries)
                                  _StructureGroup(
                                    title: entry.value,
                                    items: filtered
                                        .where(
                                            (item) => item.group == entry.key)
                                        .toList(),
                                    selectedId: _selectedId,
                                    onSelected: (id) =>
                                        setState(() => _selectedId = id),
                                  ),
                              ],
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: _selectedId == null
                      ? const Center(child: Text('Selecciona una estructura'))
                      : Column(
                          children: [
                            Wrap(
                              spacing: 12,
                              runSpacing: 8,
                              crossAxisAlignment: WrapCrossAlignment.center,
                              children: [
                                ConstrainedBox(
                                  constraints:
                                      const BoxConstraints(minWidth: 260),
                                  child: Text(
                                    selectedContent?.asData?.value.name ?? '-',
                                    overflow: TextOverflow.ellipsis,
                                    style:
                                        Theme.of(context).textTheme.titleLarge,
                                  ),
                                ),
                                DropdownButton<String>(
                                  value: _style,
                                  items: const [
                                    DropdownMenuItem(
                                      value: 'ball-stick',
                                      child: Text('Bolas y palos'),
                                    ),
                                    DropdownMenuItem(
                                      value: 'stick',
                                      child: Text('Solo enlaces'),
                                    ),
                                    DropdownMenuItem(
                                      value: 'spacefill',
                                      child: Text('Compacto'),
                                    ),
                                  ],
                                  onChanged: (value) =>
                                      setState(() => _style = value ?? _style),
                                ),
                                DropdownButton<int>(
                                  value: _supercell,
                                  items: const [
                                    DropdownMenuItem(
                                        value: 1, child: Text('1x1x1')),
                                    DropdownMenuItem(
                                        value: 2, child: Text('2x2x2')),
                                    DropdownMenuItem(
                                        value: 3, child: Text('3x3x3')),
                                  ],
                                  onChanged: (value) => setState(
                                      () => _supercell = value ?? _supercell),
                                ),
                                FilterChip(
                                  selected: _showCell,
                                  label: const Text('Celda'),
                                  onSelected: (value) =>
                                      setState(() => _showCell = value),
                                ),
                                OutlinedButton.icon(
                                  onPressed: () => guardarPng(
                                    context,
                                    _claveFigura,
                                    // El nombre sale de la formula: exportar veinte estructuras
                                    // como «figura.png» no sirve de nada.
                                    nombre: (selectedContent?.asData?.value.name ?? 'estructura')
                                        .replaceAll(RegExp(r'[^\w.-]'), '_'),
                                  ),
                                  icon: const Icon(Icons.image_outlined, size: 18),
                                  label: const Text('Exportar PNG'),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Expanded(
                              child: AsyncPanel(
                                value: selectedContent!,
                                // La captura va sobre este límite, no sobre la
                                // pantalla: sale la figura sola y a la
                                // resolución que se pida.
                                builder: (data) => RepaintBoundary(
                                  key: _claveFigura,
                                  child: CifViewer(
                                    cif: data.content,
                                    style: _style,
                                    supercell: _supercell,
                                    showCell: _showCell,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _StructureGroup extends StatelessWidget {
  const _StructureGroup({
    required this.title,
    required this.items,
    required this.selectedId,
    required this.onSelected,
  });

  final String title;
  final List<StructureItem> items;
  final String? selectedId;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final sorted = items.toList()
      ..sort((a, b) {
        if (a.group == 'recientes') {
          return (b.mtime ?? 0).compareTo(a.mtime ?? 0);
        }
        return a.name.compareTo(b.name);
      });
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${title.toUpperCase()} (${items.length})',
              style: Theme.of(context).textTheme.labelSmall),
          const SizedBox(height: 4),
          for (final item in sorted.take(80))
            ListTile(
              dense: true,
              selected: item.id == selectedId,
              title:
                  Text(fmtFormula(item.name), overflow: TextOverflow.ellipsis),
              subtitle: item.detail == null
                  ? null
                  : Text(item.detail!, overflow: TextOverflow.ellipsis),
              onTap: () => onSelected(item.id),
            ),
          if (sorted.length > 80)
            Padding(
              padding: const EdgeInsets.only(left: 16, top: 4),
              child: Text('+${sorted.length - 80} mas',
                  style: Theme.of(context).textTheme.bodySmall),
            ),
        ],
      ),
    );
  }
}
