// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'summary_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SummaryResponse _$SummaryResponseFromJson(
  Map<String, dynamic> json,
) => $checkedCreate(
  'SummaryResponse',
  json,
  ($checkedConvert) {
    $checkKeys(
      json,
      requiredKeys: const [
        'n_pending',
        'n_running',
        'n_converged',
        'n_failed',
        'n_stalled',
        'n_oscillating',
        'total',
      ],
    );
    final val = SummaryResponse(
      nPending: $checkedConvert('n_pending', (v) => (v as num).toInt()),
      nRunning: $checkedConvert('n_running', (v) => (v as num).toInt()),
      nConverged: $checkedConvert('n_converged', (v) => (v as num).toInt()),
      nFailed: $checkedConvert('n_failed', (v) => (v as num).toInt()),
      nStalled: $checkedConvert('n_stalled', (v) => (v as num).toInt()),
      nOscillating: $checkedConvert('n_oscillating', (v) => (v as num).toInt()),
      nSkippedDuplicate: $checkedConvert(
        'n_skipped_duplicate',
        (v) => (v as num?)?.toInt(),
      ),
      total: $checkedConvert('total', (v) => (v as num).toInt()),
      convergenceRate: $checkedConvert('convergence_rate', (v) => v as num?),
    );
    return val;
  },
  fieldKeyMap: const {
    'nPending': 'n_pending',
    'nRunning': 'n_running',
    'nConverged': 'n_converged',
    'nFailed': 'n_failed',
    'nStalled': 'n_stalled',
    'nOscillating': 'n_oscillating',
    'nSkippedDuplicate': 'n_skipped_duplicate',
    'convergenceRate': 'convergence_rate',
  },
);

Map<String, dynamic> _$SummaryResponseToJson(SummaryResponse instance) =>
    <String, dynamic>{
      'n_pending': instance.nPending,
      'n_running': instance.nRunning,
      'n_converged': instance.nConverged,
      'n_failed': instance.nFailed,
      'n_stalled': instance.nStalled,
      'n_oscillating': instance.nOscillating,
      'n_skipped_duplicate': ?instance.nSkippedDuplicate,
      'total': instance.total,
      'convergence_rate': ?instance.convergenceRate,
    };
