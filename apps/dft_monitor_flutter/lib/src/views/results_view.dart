import '../widgets/log_vivo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../widgets/async_panel.dart';

class ResultsView extends ConsumerStatefulWidget {
  const ResultsView({super.key});

  @override
  ConsumerState<ResultsView> createState() => _ResultsViewState();
}

class _ResultsViewState extends ConsumerState<ResultsView> {
  String? _selectedPath;

  @override
  Widget build(BuildContext context) {
    final reports = ref.watch(reportsProvider);

    return AsyncPanel(
      value: reports,
      builder: (data) {
        final active = _selectedPath ??
            (data.documents.isNotEmpty ? data.documents.first.path : null);
        final document =
            active == null ? null : ref.watch(reportDocumentProvider(active));
        if (_selectedPath == null && active != null) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted && _selectedPath == null) {
              setState(() => _selectedPath = active);
            }
          });
        }

        return LayoutBuilder(
          builder: (context, constraints) {
            final documentWidth =
                (constraints.maxWidth * 0.20).clamp(300.0, 460.0).toDouble();
            final galleryWidth =
                (constraints.maxWidth * 0.26).clamp(360.0, 560.0).toDouble();
            final galleryHeight =
                (constraints.maxHeight * 0.25).clamp(240.0, 340.0).toDouble();
            return Row(
              children: [
                SizedBox(
                  width: documentWidth,
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Documentos (${data.documents.length})',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 8),
                          Expanded(
                            child: ListView(
                              children: [
                                for (final doc in data.documents)
                                  ListTile(
                                    dense: true,
                                    selected: doc.path == active,
                                    title: Text(doc.name,
                                        overflow: TextOverflow.ellipsis),
                                    subtitle: Text(doc.group,
                                        overflow: TextOverflow.ellipsis),
                                    onTap: () => setState(
                                        () => _selectedPath = doc.path),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    children: [
                      // El log en vivo va arriba: mientras corre un lote es lo que se
                      // viene a mirar a esta pestaña.
                      SizedBox(
                        height: galleryHeight,
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Log de GPAW en vivo',
                                    style: Theme.of(context).textTheme.titleMedium),
                                const SizedBox(height: 8),
                                const Expanded(child: LogVivo()),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Expanded(
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: document == null
                                ? const Center(child: Text('Sin documentos'))
                                : AsyncPanel(
                                    value: document,
                                    builder: (doc) =>
                                        _ReportText(document: doc),
                                  ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        height: galleryHeight,
                        child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemCount: data.galleries.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(width: 12),
                          itemBuilder: (context, index) => _GalleryCard(
                            gallery: data.galleries[index],
                            width: galleryWidth,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

class _ReportText extends StatelessWidget {
  const _ReportText({required this.document});

  final ReportDocument document;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(document.name, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Expanded(
          child: SingleChildScrollView(
            child: SelectableText(
              document.content,
              style: const TextStyle(
                  fontFamily: 'monospace', fontSize: 13, height: 1.35),
            ),
          ),
        ),
      ],
    );
  }
}

class _GalleryCard extends ConsumerWidget {
  const _GalleryCard({required this.gallery, required this.width});

  final Gallery gallery;
  final double width;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // `Image.network` solo decodifica mapas de bits. Los manifiestos declaran
    // un PDF por cada PNG —95 de 190 en este proyecto—, y pintarlos en la
    // rejilla daba casillas rotas: eso era «el visualizador no carga las
    // figuras».
    const rasterizables = ['.png', '.jpg', '.jpeg', '.webp'];
    final enDisco = gallery.figures.where((f) => f.present).toList();
    final present = enDisco
        .where((f) => rasterizables.any(f.path.toLowerCase().endsWith))
        .toList();
    final otros = enDisco.length - present.length;
    return SizedBox(
      width: width,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(gallery.name,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium),
                  ),
                  Text(
                    otros > 0
                        ? '${present.length}/${gallery.nDeclared} · $otros no visualizables'
                        : '${gallery.nPresent}/${gallery.nDeclared}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: present.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Text(
                            gallery.nDeclared == 0
                                ? 'Esta galería no declara figuras.'
                                : 'Ninguna de las ${gallery.nDeclared} figuras está en '
                                    'disco. Los PNG están en .gitignore: regenéralos '
                                    'con scripts/generate_visualizations.py',
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      )
                    : GridView.builder(
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          crossAxisSpacing: 8,
                          mainAxisSpacing: 8,
                        ),
                        itemCount: present.length,
                        itemBuilder: (context, index) {
                          final figure = present[index];
                          final url =
                              ref.watch(reportFigureUrlProvider(figure.path));
                          return Tooltip(
                            message: figure.name,
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(6),
                              child: Image.network(
                                url,
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(
                                  color: const Color(0xff111827),
                                  alignment: Alignment.center,
                                  child:
                                      const Icon(Icons.broken_image_outlined),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
