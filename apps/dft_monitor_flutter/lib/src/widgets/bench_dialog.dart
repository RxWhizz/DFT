import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/errors.dart';
import '../models/bench.dart';
import '../repositories/repositories.dart';

/// Ofrece medir cuántos jobs concurrentes y cuántos núcleos por job aguanta
/// esta máquina.
///
/// El barrido lanza cálculos GPAW reales y tarda: el rápido unos minutos, el
/// completo horas. Por eso la caja dice de antemano cuántos repartos va a
/// probar y avisa si la máquina está ocupada, en vez de arrancar a ciegas.
Future<void> showBenchDialog(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (_) => const _BenchDialog(),
  );
}

class _BenchDialog extends ConsumerWidget {
  const _BenchDialog();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final estado = ref.watch(benchStatusProvider);

    return AlertDialog(
      title: const Text('Calibrar rendimiento'),
      content: SizedBox(
        width: 520,
        child: estado.when(
          skipLoadingOnReload: true,
          loading: () => const SizedBox(
              height: 120, child: Center(child: CircularProgressIndicator())),
          error: (e, _) => Text(mensajeDeError(e)),
          data: (d) => _Cuerpo(estado: d),
        ),
      ),
      actions: _acciones(context, ref, estado.valueOrNull),
    );
  }

  List<Widget> _acciones(BuildContext context, WidgetRef ref, BenchStatus? d) {
    if (d == null) {
      return [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
      ];
    }

    if (d.running) {
      return [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
        TextButton(
          onPressed: () => _cancelar(context, ref),
          style: TextButton.styleFrom(
              foregroundColor: Theme.of(context).colorScheme.error),
          child: const Text('Detener'),
        ),
      ];
    }

    final bloqueado = !d.canRun || !d.machine.available;
    return [
      TextButton(
          onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
      TextButton(
        onPressed: bloqueado ? null : () => _lanzar(context, ref, d, 'full'),
        child: const Text('Barrido completo'),
      ),
      FilledButton(
        onPressed: bloqueado ? null : () => _lanzar(context, ref, d, 'quick'),
        child: const Text('Medición rápida'),
      ),
    ];
  }

  Future<void> _lanzar(
      BuildContext context, WidgetRef ref, BenchStatus d, String modo) async {
    // Con la máquina ocupada el backend responde 409. Se pregunta antes en vez
    // de enseñar un error: medir así infla el t/iter y recomendaría menos slots
    // de los que la máquina aguanta.
    var force = false;
    if (d.busy.isNotEmpty) {
      final seguir = await showDialog<bool>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('La máquina está calculando'),
          content: Text(
            'Hay ${d.busy.length} cálculo(s) en marcha. Medir ahora daría un '
            'tiempo por iteración inflado y recomendaría menos slots de los que '
            'la máquina aguanta, además de robarle núcleos al trabajo real.\n\n'
            '¿Medir de todas formas?',
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Esperar')),
            FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Medir igual')),
          ],
        ),
      );
      if (seguir != true) return;
      force = true;
    }

    try {
      await ref.read(benchActionsProvider).run(mode: modo, force: force);
      ref.invalidate(benchStatusProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(modo == 'quick'
              ? 'Medición rápida iniciada.'
              : 'Barrido completo iniciado. Puede tardar horas.'),
        ));
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
      }
    }
  }

  Future<void> _cancelar(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(benchActionsProvider).cancel();
      ref.invalidate(benchStatusProvider);
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
      }
    }
  }
}


class _Cuerpo extends StatelessWidget {
  const _Cuerpo({required this.estado});

  final BenchStatus estado;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final hijos = <Widget>[];

    // ── La máquina ───────────────────────────────────────────────────────────
    if (!estado.machine.available) {
      hijos.add(_Aviso(
        icono: Icons.error_outline,
        color: t.colorScheme.error,
        texto: estado.machine.reason ??
            'No se puede inspeccionar esta máquina.',
      ));
    } else {
      hijos.add(Text(estado.machine.description, style: t.textTheme.bodyMedium));
      hijos.add(const SizedBox(height: 16));
    }

    // ── Qué hay medido ──────────────────────────────────────────────────────
    final cal = estado.calibration;
    if (cal != null) {
      hijos.add(_Fila('Óptimo medido', '${cal.split} jobs×núcleos'));
      hijos.add(_Fila('Throughput', '${cal.throughput} iters/s'));
      hijos.add(_Fila('RAM en el pico', '${cal.peakRamGb} GB'));
      hijos.add(_Fila('Medido el', cal.measuredAt.split('T').first));
      hijos.add(_Fila('Configurado', estado.configuredSplit));
      if (estado.differsFromConfig) {
        hijos.add(const SizedBox(height: 12));
        hijos.add(_Aviso(
          icono: Icons.info_outline,
          color: t.colorScheme.tertiary,
          texto: 'La configuración usa ${estado.configuredSplit} pero se midió '
              '${cal.split} como óptimo. Ajusta runner_slots y runner_cores '
              'en monitor.yaml para aprovecharlo.',
        ));
      }
    } else if (estado.machine.available) {
      hijos.add(_Aviso(
        icono: Icons.help_outline,
        color: t.colorScheme.onSurfaceVariant,
        texto: 'Esta máquina no se ha medido nunca. La configuración actual '
            '(${estado.configuredSplit}) está puesta a mano.',
      ));
    }

    // ── En marcha ────────────────────────────────────────────────────────────
    if (estado.running) {
      hijos.add(const SizedBox(height: 16));
      hijos.add(LinearProgressIndicator(
          value: estado.total > 0 ? estado.progress : null));
      hijos.add(const SizedBox(height: 8));
      hijos.add(Text(
        estado.total > 0
            ? 'Midiendo ${estado.current ?? ""} — ${estado.done} de ${estado.total} repartos'
            : 'Preparando la medición…',
        style: t.textTheme.bodySmall,
      ));
    } else {
      if (estado.status == 'interrupted') {
        hijos.add(const SizedBox(height: 12));
        hijos.add(_Aviso(
          icono: Icons.warning_amber_outlined,
          color: t.colorScheme.error,
          texto: 'El último barrido se interrumpió sin terminar.',
        ));
      } else if (estado.error != null) {
        hijos.add(const SizedBox(height: 12));
        hijos.add(_Aviso(
            icono: Icons.error_outline,
            color: t.colorScheme.error,
            texto: estado.error!));
      }

      if (estado.machine.available && estado.canRun) {
        hijos.add(const SizedBox(height: 16));
        hijos.add(Text('Qué se va a medir', style: t.textTheme.titleSmall));
        hijos.add(const SizedBox(height: 6));
        hijos.add(Text(
          'Para cada reparto se lanzan N jobs GPAW a la vez y se mide el '
          'throughput agregado y el pico de RAM. Gana el que más rinde sin '
          'salirse de la memoria.',
          style: t.textTheme.bodySmall,
        ));
        hijos.add(const SizedBox(height: 10));
        hijos.add(_Fila('Medición rápida',
            '${estado.machine.nSplitsQuick} repartos · minutos'));
        hijos.add(_Fila('Barrido completo',
            '${estado.machine.nSplitsFull} repartos · horas'));
      }

      if (!estado.canRun && estado.machine.available) {
        hijos.add(const SizedBox(height: 12));
        hijos.add(_Aviso(
          icono: Icons.block,
          color: t.colorScheme.error,
          texto: 'Esta instalación no puede medir: falta un intérprete de '
              'Python o los scripts del pipeline. La app de escritorio '
              'necesita el repositorio para el barrido.',
        ));
      }

      if (estado.busy.isNotEmpty) {
        hijos.add(const SizedBox(height: 12));
        hijos.add(_Aviso(
          icono: Icons.hourglass_top,
          color: t.colorScheme.error,
          texto: 'Hay ${estado.busy.length} cálculo(s) en marcha. Medir ahora '
              'daría números falseados.',
        ));
      }
    }

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: hijos,
      ),
    );
  }
}


class _Fila extends StatelessWidget {
  const _Fila(this.etiqueta, this.valor);

  final String etiqueta;
  final String valor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(etiqueta, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(child: Text(valor)),
        ],
      ),
    );
  }
}


class _Aviso extends StatelessWidget {
  const _Aviso({required this.icono, required this.color, required this.texto});

  final IconData icono;
  final Color color;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icono, size: 18, color: color),
        const SizedBox(width: 8),
        Expanded(
          child: Text(texto,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: color)),
        ),
      ],
    );
  }
}
