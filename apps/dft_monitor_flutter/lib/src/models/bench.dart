/// Estado de la calibración de rendimiento de la máquina.
class BenchMachine {
  const BenchMachine({
    required this.available,
    required this.description,
    required this.physicalCores,
    required this.logicalCores,
    required this.ramTotalGb,
    required this.budgets,
    required this.nSplitsQuick,
    required this.nSplitsFull,
    this.reason,
  });

  factory BenchMachine.fromJson(Map<String, dynamic> json) => BenchMachine(
        available: json['available'] == true,
        description: json['description'] as String? ?? '-',
        physicalCores: (json['physical_cores'] as num? ?? 0).toInt(),
        logicalCores: (json['logical_cores'] as num? ?? 0).toInt(),
        ramTotalGb: (json['ram_total_gb'] as num? ?? 0).toDouble(),
        budgets: ((json['budgets'] as List?) ?? const [])
            .map((e) => (e as num).toInt())
            .toList(),
        nSplitsQuick: (json['n_splits_quick'] as num? ?? 0).toInt(),
        nSplitsFull: (json['n_splits_full'] as num? ?? 0).toInt(),
        reason: json['reason'] as String?,
      );

  final bool available;
  final String description;
  final int physicalCores;
  final int logicalCores;
  final double ramTotalGb;
  final List<int> budgets;
  final int nSplitsQuick;
  final int nSplitsFull;

  /// Por qué no se puede medir, cuando `available` es falso.
  final String? reason;
}

class BenchCalibration {
  const BenchCalibration({
    required this.slots,
    required this.cores,
    required this.throughput,
    required this.peakRamGb,
    required this.measuredAt,
  });

  factory BenchCalibration.fromJson(Map<String, dynamic> json) => BenchCalibration(
        slots: (json['best_slots'] as num? ?? 0).toInt(),
        cores: (json['best_cores'] as num? ?? 0).toInt(),
        throughput: (json['throughput'] as num? ?? 0).toDouble(),
        peakRamGb: (json['peak_ram_gb'] as num? ?? 0).toDouble(),
        measuredAt: json['measured_at'] as String? ?? '',
      );

  final int slots;
  final int cores;
  final double throughput;
  final double peakRamGb;
  final String measuredAt;

  String get split => '${slots}x$cores';
}

class BenchStatus {
  const BenchStatus({
    required this.status,
    required this.running,
    required this.done,
    required this.total,
    required this.canRun,
    required this.machine,
    required this.busy,
    required this.configuredSlots,
    required this.configuredCores,
    this.current,
    this.error,
    this.calibration,
  });

  factory BenchStatus.fromJson(Map<String, dynamic> json) => BenchStatus(
        status: json['status'] as String? ?? 'idle',
        running: json['running'] == true,
        done: (json['done'] as num? ?? 0).toInt(),
        total: (json['total'] as num? ?? 0).toInt(),
        canRun: json['can_run'] == true,
        machine: BenchMachine.fromJson(
            Map<String, dynamic>.from(json['machine'] as Map? ?? {})),
        busy: ((json['busy'] as List?) ?? const []).map((e) => '$e').toList(),
        configuredSlots: (json['configured_slots'] as num? ?? 0).toInt(),
        configuredCores: (json['configured_cores'] as num? ?? 0).toInt(),
        current: json['current'] as String?,
        error: json['error'] as String?,
        calibration: json['calibration'] == null
            ? null
            : BenchCalibration.fromJson(
                Map<String, dynamic>.from(json['calibration'] as Map)),
      );

  final String status;
  final bool running;
  final int done;
  final int total;
  final bool canRun;
  final BenchMachine machine;

  /// Cálculos en marcha que falsearían la medición.
  final List<String> busy;

  final int configuredSlots;
  final int configuredCores;
  final String? current;
  final String? error;
  final BenchCalibration? calibration;

  String get configuredSplit => '${configuredSlots}x$configuredCores';

  /// Si lo medido y lo configurado no coinciden, merece decirlo.
  bool get differsFromConfig =>
      calibration != null &&
      (calibration!.slots != configuredSlots || calibration!.cores != configuredCores);

  double get progress => total > 0 ? done / total : 0;
}
