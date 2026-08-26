// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'ping_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PingResponse _$PingResponseFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'PingResponse',
      json,
      ($checkedConvert) {
        $checkKeys(json, requiredKeys: const ['job_id', 'alive']);
        final val = PingResponse(
          jobId: $checkedConvert('job_id', (v) => v as String),
          alive: $checkedConvert('alive', (v) => v as bool),
          currentStep: $checkedConvert(
            'current_step',
            (v) => (v as num?)?.toInt(),
          ),
          stepType: $checkedConvert('step_type', (v) => v as String?),
          energyEv: $checkedConvert('energy_ev', (v) => v as num?),
          fmaxEvAng: $checkedConvert('fmax_ev_ang', (v) => v as num?),
          memoryRssMb: $checkedConvert(
            'memory_rss_mb',
            (v) => (v as num?)?.toInt(),
          ),
          tIterS: $checkedConvert('t_iter_s', (v) => v as num?),
          etaMin: $checkedConvert('eta_min', (v) => v as num?),
          logLastLine: $checkedConvert('log_last_line', (v) => v as String?),
          status: $checkedConvert(
            'status',
            (v) => $enumDecodeNullable(_$PingResponseStatusEnumEnumMap, v),
          ),
        );
        return val;
      },
      fieldKeyMap: const {
        'jobId': 'job_id',
        'currentStep': 'current_step',
        'stepType': 'step_type',
        'energyEv': 'energy_ev',
        'fmaxEvAng': 'fmax_ev_ang',
        'memoryRssMb': 'memory_rss_mb',
        'tIterS': 't_iter_s',
        'etaMin': 'eta_min',
        'logLastLine': 'log_last_line',
      },
    );

Map<String, dynamic> _$PingResponseToJson(PingResponse instance) =>
    <String, dynamic>{
      'job_id': instance.jobId,
      'alive': instance.alive,
      'current_step': ?instance.currentStep,
      'step_type': ?instance.stepType,
      'energy_ev': ?instance.energyEv,
      'fmax_ev_ang': ?instance.fmaxEvAng,
      'memory_rss_mb': ?instance.memoryRssMb,
      't_iter_s': ?instance.tIterS,
      'eta_min': ?instance.etaMin,
      'log_last_line': ?instance.logLastLine,
      'status': ?_$PingResponseStatusEnumEnumMap[instance.status],
    };

const _$PingResponseStatusEnumEnumMap = {
  PingResponseStatusEnum.pending: 'pending',
  PingResponseStatusEnum.running: 'running',
  PingResponseStatusEnum.converged: 'converged',
  PingResponseStatusEnum.partial: 'partial',
  PingResponseStatusEnum.failed: 'failed',
  PingResponseStatusEnum.stalled: 'stalled',
  PingResponseStatusEnum.oscillating: 'oscillating',
  PingResponseStatusEnum.stopped: 'stopped',
  PingResponseStatusEnum.skippedDuplicate: 'skipped_duplicate',
  PingResponseStatusEnum.unknown: 'unknown',
};
