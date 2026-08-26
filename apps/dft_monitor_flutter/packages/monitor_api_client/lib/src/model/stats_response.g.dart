// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'stats_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

StatsResponse _$StatsResponseFromJson(
  Map<String, dynamic> json,
) => $checkedCreate(
  'StatsResponse',
  json,
  ($checkedConvert) {
    $checkKeys(json, requiredKeys: const ['job_id', 'formula', 'status']);
    final val = StatsResponse(
      jobId: $checkedConvert('job_id', (v) => v as String),
      formula: $checkedConvert('formula', (v) => v as String),
      status: $checkedConvert(
        'status',
        (v) => $enumDecode(_$StatsResponseStatusEnumEnumMap, v),
      ),
      pid: $checkedConvert('pid', (v) => (v as num?)?.toInt()),
      startTime: $checkedConvert('start_time', (v) => v as String?),
      elapsedMin: $checkedConvert('elapsed_min', (v) => v as num?),
      mpiCores: $checkedConvert('mpi_cores', (v) => (v as num?)?.toInt()),
      energyHistory: $checkedConvert(
        'energy_history',
        (v) => (v as List<dynamic>?)?.map((e) => e as num).toList(),
      ),
      fmaxHistory: $checkedConvert(
        'fmax_history',
        (v) => (v as List<dynamic>?)?.map((e) => e as num).toList(),
      ),
      scfIterHistory: $checkedConvert(
        'scf_iter_history',
        (v) => (v as List<dynamic>?)?.map((e) => (e as num).toInt()).toList(),
      ),
      nFireSteps: $checkedConvert('n_fire_steps', (v) => (v as num?)?.toInt()),
      nScfIters: $checkedConvert('n_scf_iters', (v) => (v as num?)?.toInt()),
      isOscillating: $checkedConvert('is_oscillating', (v) => v as bool?),
      stallMinutes: $checkedConvert('stall_minutes', (v) => v as num?),
      finalEnergyEv: $checkedConvert('final_energy_ev', (v) => v as num?),
    );
    return val;
  },
  fieldKeyMap: const {
    'jobId': 'job_id',
    'startTime': 'start_time',
    'elapsedMin': 'elapsed_min',
    'mpiCores': 'mpi_cores',
    'energyHistory': 'energy_history',
    'fmaxHistory': 'fmax_history',
    'scfIterHistory': 'scf_iter_history',
    'nFireSteps': 'n_fire_steps',
    'nScfIters': 'n_scf_iters',
    'isOscillating': 'is_oscillating',
    'stallMinutes': 'stall_minutes',
    'finalEnergyEv': 'final_energy_ev',
  },
);

Map<String, dynamic> _$StatsResponseToJson(StatsResponse instance) =>
    <String, dynamic>{
      'job_id': instance.jobId,
      'formula': instance.formula,
      'status': _$StatsResponseStatusEnumEnumMap[instance.status]!,
      'pid': ?instance.pid,
      'start_time': ?instance.startTime,
      'elapsed_min': ?instance.elapsedMin,
      'mpi_cores': ?instance.mpiCores,
      'energy_history': ?instance.energyHistory,
      'fmax_history': ?instance.fmaxHistory,
      'scf_iter_history': ?instance.scfIterHistory,
      'n_fire_steps': ?instance.nFireSteps,
      'n_scf_iters': ?instance.nScfIters,
      'is_oscillating': ?instance.isOscillating,
      'stall_minutes': ?instance.stallMinutes,
      'final_energy_ev': ?instance.finalEnergyEv,
    };

const _$StatsResponseStatusEnumEnumMap = {
  StatsResponseStatusEnum.pending: 'pending',
  StatsResponseStatusEnum.running: 'running',
  StatsResponseStatusEnum.converged: 'converged',
  StatsResponseStatusEnum.partial: 'partial',
  StatsResponseStatusEnum.failed: 'failed',
  StatsResponseStatusEnum.stalled: 'stalled',
  StatsResponseStatusEnum.oscillating: 'oscillating',
  StatsResponseStatusEnum.stopped: 'stopped',
  StatsResponseStatusEnum.skippedDuplicate: 'skipped_duplicate',
  StatsResponseStatusEnum.unknown: 'unknown',
};
