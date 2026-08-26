import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../repositories/repositories.dart';

/// Franja que dice qué está pasando y cuánto queda.
///
/// Las vistas mostraban recuentos —12 pendientes, 2 corriendo— pero no
/// respondían de un vistazo a «¿está haciendo algo?». Y sin tiempo estimado, un
/// lote de cincuenta jobs es una barra que no se mueve.
class ActivityBanner extends ConsumerWidget {
  const ActivityBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final act = ref.watch(activityProvider);
    final d = act.valueOrNull;
    if (d == null) return const SizedBox.shrink();

    final t = Theme.of(context);
    final (icono, color) = switch (d.activity) {
      'dft' => (Icons.memory, t.colorScheme.primary),
      'queued' => (Icons.schedule, t.colorScheme.tertiary),
      'generating' => (Icons.auto_awesome, t.colorScheme.tertiary),
      'benchmark' => (Icons.speed, t.colorScheme.tertiary),
      _ => (Icons.pause_circle_outline, t.colorScheme.onSurfaceVariant),
    };

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                // Solo gira cuando de verdad hay trabajo: un indicador que gira
                // en reposo enseña a ignorarlo.
                if (d.busy)
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: color),
                  )
                else
                  Icon(icono, size: 18, color: color),
                const SizedBox(width: 10),
                Text(d.label,
                    style: t.textTheme.titleSmall?.copyWith(
                        color: color, fontWeight: FontWeight.w600)),
                if (d.detail != null) ...[
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(d.detail!,
                        style: t.textTheme.bodySmall,
                        overflow: TextOverflow.ellipsis),
                  ),
                ] else
                  const Spacer(),
                if (d.etaText != null)
                  Tooltip(
                    message: d.etaBasis ?? '',
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('Tiempo estimado ',
                            style: t.textTheme.bodySmall?.copyWith(
                                color: t.colorScheme.onSurfaceVariant)),
                        Text(d.etaText!,
                            style: t.textTheme.titleSmall?.copyWith(
                                fontWeight: FontWeight.w600)),
                      ],
                    ),
                  )
                else if (d.busy && d.activity != 'generating')
                  Text('Tiempo estimado: sin datos',
                      style: t.textTheme.bodySmall?.copyWith(
                          color: t.colorScheme.onSurfaceVariant)),
              ],
            ),
            if (d.progress != null) ...[
              const SizedBox(height: 10),
              LinearProgressIndicator(value: d.progress),
              const SizedBox(height: 4),
              Text('${d.nDone} de ${d.total} terminados',
                  style: t.textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}
