// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'screening_start_dft_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

ScreeningStartDftRequest _$ScreeningStartDftRequestFromJson(
  Map<String, dynamic> json,
) => $checkedCreate('ScreeningStartDftRequest', json, ($checkedConvert) {
  final val = ScreeningStartDftRequest(
    startRunner: $checkedConvert('start_runner', (v) => v as bool?),
  );
  return val;
}, fieldKeyMap: const {'startRunner': 'start_runner'});

Map<String, dynamic> _$ScreeningStartDftRequestToJson(
  ScreeningStartDftRequest instance,
) => <String, dynamic>{'start_runner': ?instance.startRunner};
