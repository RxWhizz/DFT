// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'screening_run_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ScreeningRunRequest _$ScreeningRunRequestFromJson(
  Map<String, dynamic> json,
) => $checkedCreate(
  'ScreeningRunRequest',
  json,
  ($checkedConvert) {
    final val = ScreeningRunRequest(
      batchId: $checkedConvert('batch_id', (v) => (v as num?)?.toInt()),
      nCandidates: $checkedConvert('n_candidates', (v) => (v as num?)?.toInt()),
      nBatches: $checkedConvert('n_batches', (v) => (v as num?)?.toInt()),
      randomSeed: $checkedConvert('random_seed', (v) => (v as num?)?.toInt()),
      useMlff: $checkedConvert('use_mlff', (v) => v as bool?),
    );
    return val;
  },
  fieldKeyMap: const {
    'batchId': 'batch_id',
    'nCandidates': 'n_candidates',
    'nBatches': 'n_batches',
    'randomSeed': 'random_seed',
    'useMlff': 'use_mlff',
  },
);

Map<String, dynamic> _$ScreeningRunRequestToJson(
  ScreeningRunRequest instance,
) => <String, dynamic>{
  'batch_id': ?instance.batchId,
  'n_candidates': ?instance.nCandidates,
  'n_batches': ?instance.nBatches,
  'random_seed': ?instance.randomSeed,
  'use_mlff': ?instance.useMlff,
};
