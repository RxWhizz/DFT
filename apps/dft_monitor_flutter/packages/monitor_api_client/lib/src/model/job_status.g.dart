// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'job_status.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

JobStatus _$JobStatusFromJson(Map<String, dynamic> json) => $checkedCreate(
  'JobStatus',
  json,
  ($checkedConvert) {
    $checkKeys(json, requiredKeys: const ['job_id', 'formula', 'status']);
    final val = JobStatus(
      jobId: $checkedConvert('job_id', (v) => v as String),
      formula: $checkedConvert('formula', (v) => v as String),
      status: $checkedConvert(
        'status',
        (v) => $enumDecode(_$JobStatusStatusEnumEnumMap, v),
      ),
      pid: $checkedConvert('pid', (v) => (v as num?)?.toInt()),
      startTime: $checkedConvert('start_time', (v) => v as String?),
      elapsedMin: $checkedConvert('elapsed_min', (v) => v as num?),
      mpiCores: $checkedConvert('mpi_cores', (v) => (v as num?)?.toInt()),
    );
    return val;
  },
  fieldKeyMap: const {
    'jobId': 'job_id',
    'startTime': 'start_time',
    'elapsedMin': 'elapsed_min',
    'mpiCores': 'mpi_cores',
  },
);

Map<String, dynamic> _$JobStatusToJson(JobStatus instance) => <String, dynamic>{
  'job_id': instance.jobId,
  'formula': instance.formula,
  'status': _$JobStatusStatusEnumEnumMap[instance.status]!,
  'pid': ?instance.pid,
  'start_time': ?instance.startTime,
  'elapsed_min': ?instance.elapsedMin,
  'mpi_cores': ?instance.mpiCores,
};

const _$JobStatusStatusEnumEnumMap = {
  JobStatusStatusEnum.pending: 'pending',
  JobStatusStatusEnum.running: 'running',
  JobStatusStatusEnum.converged: 'converged',
  JobStatusStatusEnum.partial: 'partial',
  JobStatusStatusEnum.failed: 'failed',
  JobStatusStatusEnum.stalled: 'stalled',
  JobStatusStatusEnum.oscillating: 'oscillating',
  JobStatusStatusEnum.stopped: 'stopped',
  JobStatusStatusEnum.skippedDuplicate: 'skipped_duplicate',
  JobStatusStatusEnum.unknown: 'unknown',
};
