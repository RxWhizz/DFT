import '../models/activity.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/errors.dart';
import '../repositories/repositories.dart';

/// Cola del log de GPAW de los trabajos que están calculando ahora.
///
/// El log ya se servía por `/api/jobs/{id}/log`, pero solo se veía entrando al
/// detalle de un trabajo concreto. Mientras corre un lote, lo que se quiere es
/// mirar el SCF avanzar sin ir buscando cuál de los cincuenta está vivo.
class LogVivo extends ConsumerStatefulWidget {
  const LogVivo({super.key});

  @override
  ConsumerState<LogVivo> createState() => _LogVivoState();
}

class _LogVivoState extends ConsumerState<LogVivo> {
  String? _jobId;
  String? _etiqueta;
  bool _seguir = true;
  final ScrollController _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _alFondo() {
    // Tras el fotograma: antes de pintar, `maxScrollExtent` es el de la lista
    // anterior y el salto se queda corto.
    if (!_seguir) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final actividad = ref.watch(activityProvider);

    return actividad.when(
      skipLoadingOnReload: true,
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(mensajeDeError(e))),
      data: (act) {
        final jobs = act.runningJobs;
        if (jobs.isEmpty) {
          return const Center(
            child: Text('No hay cálculos en marcha.\n'
                'El log aparece aquí cuando el runner arranca un trabajo.',
                textAlign: TextAlign.center),
          );
        }

        // Si el trabajo que se miraba terminó, se pasa al primero vivo en vez
        // de dejar la vista congelada en un log que ya no avanza.
        final ids = jobs.map((j) => j.jobId).toList();
        final actual = (_jobId != null && ids.contains(_jobId)) ? _jobId! : ids.first;
        if (actual != _jobId) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) setState(() => _jobId = actual);
          });
        }

        final log = ref.watch(jobLogProvider(
            JobLogPeticion(jobId: actual, etiqueta: _etiqueta)));

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _Barra(
              jobs: jobs,
              seleccionado: actual,
              etiqueta: _etiqueta,
              etiquetas: log.asData?.value.disponibles ?? const [],
              seguir: _seguir,
              onJob: (v) => setState(() {
                _jobId = v;
                _etiqueta = null;   // otro trabajo puede tener otros ficheros
              }),
              onEtiqueta: (v) => setState(() => _etiqueta = v),
              onSeguir: (v) => setState(() => _seguir = v),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: log.when(
                skipLoadingOnReload: true,
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(child: Text(mensajeDeError(e))),
                data: (datos) {
                  if (datos.lineas.isEmpty) {
                    return const Center(
                        child: Text('El trabajo aún no ha escrito nada.'));
                  }
                  _alFondo();
                  return Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surfaceContainerLowest,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Scrollbar(
                      controller: _scroll,
                      child: ListView.builder(
                        controller: _scroll,
                        itemCount: datos.lineas.length,
                        itemBuilder: (context, i) => Text(
                          datos.lineas[i],
                          style: const TextStyle(
                              fontFamily: 'monospace', fontSize: 11.5),
                        ),
                      ),
                    ),
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


class _Barra extends StatelessWidget {
  const _Barra({
    required this.jobs,
    required this.seleccionado,
    required this.etiqueta,
    required this.etiquetas,
    required this.seguir,
    required this.onJob,
    required this.onEtiqueta,
    required this.onSeguir,
  });

  final List<TrabajoVivo> jobs;
  final String seleccionado;
  final String? etiqueta;
  final List<String> etiquetas;
  final bool seguir;
  final ValueChanged<String> onJob;
  final ValueChanged<String?> onEtiqueta;
  final ValueChanged<bool> onSeguir;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        DropdownButton<String>(
          value: seleccionado,
          items: [
            for (final j in jobs)
              DropdownMenuItem(
                value: j.jobId,
                child: Text('${j.formula} · ${j.jobId.substring(0, 8)}'),
              ),
          ],
          onChanged: (v) => v == null ? null : onJob(v),
        ),
        if (etiquetas.length > 1)
          DropdownButton<String?>(
            value: etiqueta,
            hint: const Text('archivo'),
            items: [
              const DropdownMenuItem(value: null, child: Text('principal')),
              for (final e in etiquetas)
                DropdownMenuItem(value: e, child: Text(e)),
            ],
            onChanged: onEtiqueta,
          ),
        FilterChip(
          selected: seguir,
          label: const Text('Seguir el final'),
          onSelected: onSeguir,
        ),
      ],
    );
  }
}
