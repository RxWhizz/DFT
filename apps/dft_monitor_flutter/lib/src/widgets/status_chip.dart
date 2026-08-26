import 'package:flutter/material.dart';

class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'converged' => Colors.greenAccent,
      'running' => Colors.lightBlueAccent,
      'failed' || 'stopped' => Colors.redAccent,
      'stalled' || 'oscillating' => Colors.amberAccent,
      'pending' => Colors.grey,
      _ => Colors.blueGrey,
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(_enEspanol(status),
          style: TextStyle(color: color, fontSize: 12)),
    );
  }
}

/// Los estados llegan de la API en inglés; se muestran traducidos.
///
/// Un estado desconocido se enseña tal cual: es preferible un término en inglés
/// a ocultar que el backend devolvió algo que la interfaz no contempla.
String _enEspanol(String status) => switch (status) {
      'converged' => 'convergido',
      'running' => 'calculando',
      'failed' => 'fallido',
      'stopped' => 'detenido',
      'stalled' => 'estancado',
      'oscillating' => 'oscilando',
      'pending' => 'en cola',
      'skipped_duplicate' => 'duplicado',
      'unknown' => 'desconocido',
      _ => status,
    };
