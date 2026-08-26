// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'metrics_history_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

MetricsHistoryResponse _$MetricsHistoryResponseFromJson(
  Map<String, dynamic> json,
) => $checkedCreate('MetricsHistoryResponse', json, ($checkedConvert) {
  $checkKeys(json, requiredKeys: const ['samples', 'interval_sec']);
  final val = MetricsHistoryResponse(
    samples: $checkedConvert(
      'samples',
      (v) => (v as List<dynamic>)
          .map(
            (e) => (e as Map<String, dynamic>).map(
              (k, e) => MapEntry(k, e as Object),
            ),
          )
          .toList(),
    ),
    intervalSec: $checkedConvert('interval_sec', (v) => (v as num).toInt()),
  );
  return val;
}, fieldKeyMap: const {'intervalSec': 'interval_sec'});

Map<String, dynamic> _$MetricsHistoryResponseToJson(
  MetricsHistoryResponse instance,
) => <String, dynamic>{
  'samples': instance.samples,
  'interval_sec': instance.intervalSec,
};
