/// Qué está haciendo el sistema ahora mismo.
class Activity {
  const Activity({
    required this.activity,
    required this.label,
    required this.busy,
    required this.nPending,
    required this.nActive,
    required this.nDone,
    required this.total,
    this.detail,
    this.etaSeconds,
    this.etaText,
    this.etaBasis,
    this.progress,
    this.runningJobs = const [],
  });

  factory Activity.fromJson(Map<String, dynamic> json) {
    final activity = json['activity'] as String? ?? 'idle';
    return Activity(
      activity: activity,
      label: json['label'] as String? ?? '-',
      busy: json['busy'] as bool? ?? activity != 'idle',
      nPending: (json['n_pending'] as num? ?? 0).toInt(),
      nActive: (json['n_active'] as num? ?? 0).toInt(),
      nDone: (json['n_done'] as num? ?? 0).toInt(),
      total: (json['total'] as num? ?? 0).toInt(),
      detail: json['detail'] as String?,
      etaSeconds: (json['eta_seconds'] as num?)?.toDouble(),
      etaText: json['eta_text'] as String?,
      etaBasis: json['eta_basis'] as String?,
      progress: (json['progress'] as num?)?.toDouble(),
      runningJobs: ((json['running_jobs'] as List?) ?? const [])
          .whereType<Map>()
          .map((e) => TrabajoVivo.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }

  /// `discovery` · `dft` · `queued` · `generating` · `benchmark` · `idle`
  final String activity;
  final String label;
  final bool busy;
  final int nPending;
  final int nActive;
  final int nDone;
  final int total;
  final String? detail;
  final double? etaSeconds;

  /// Ya formateado por el servidor: «1 h 20 min».
  final String? etaText;

  /// De dónde sale la estimación. Un número sin base no sirve para planificar.
  final String? etaBasis;

  final double? progress;

  /// Trabajos del lote activo que están calculando ahora mismo.
  ///
  /// Vienen de aquí y no de `/api/jobs` porque el poller vigila un único
  /// directorio: con el runner en otro lote, aquella lista salía vacía.
  final List<TrabajoVivo> runningJobs;
}

class TrabajoVivo {
  const TrabajoVivo({
    required this.jobId,
    required this.formula,
    required this.estado,
    required this.batch,
  });

  factory TrabajoVivo.fromJson(Map<String, dynamic> json) => TrabajoVivo(
        jobId: json['job_id'] as String? ?? '?',
        formula: json['formula'] as String? ?? '?',
        estado: json['status'] as String? ?? 'running',
        batch: json['batch'] as String? ?? '',
      );

  final String jobId;
  final String formula;
  final String estado;
  final String batch;
}
