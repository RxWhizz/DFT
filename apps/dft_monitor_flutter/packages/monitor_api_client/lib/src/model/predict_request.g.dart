// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'predict_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PredictRequest _$PredictRequestFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'PredictRequest',
      json,
      ($checkedConvert) {
        $checkKeys(json, requiredKeys: const ['A', 'B', 'X']);
        final val = PredictRequest(
          A: $checkedConvert('A', (v) => v as String),
          B: $checkedConvert('B', (v) => v as String),
          X: $checkedConvert('X', (v) => v as String),
          aLat: $checkedConvert('a_lat', (v) => v as num?),
          eMaceEvAtom: $checkedConvert('e_mace_ev_atom', (v) => v as num?),
          bandGapGgaEv: $checkedConvert('band_gap_gga_ev', (v) => v as num?),
          eformEvAtom: $checkedConvert('eform_ev_atom', (v) => v as num?),
          material: $checkedConvert('material', (v) => v as String?),
        );
        return val;
      },
      fieldKeyMap: const {
        'aLat': 'a_lat',
        'eMaceEvAtom': 'e_mace_ev_atom',
        'bandGapGgaEv': 'band_gap_gga_ev',
        'eformEvAtom': 'eform_ev_atom',
      },
    );

Map<String, dynamic> _$PredictRequestToJson(PredictRequest instance) =>
    <String, dynamic>{
      'A': instance.A,
      'B': instance.B,
      'X': instance.X,
      'a_lat': ?instance.aLat,
      'e_mace_ev_atom': ?instance.eMaceEvAtom,
      'band_gap_gga_ev': ?instance.bandGapGgaEv,
      'eform_ev_atom': ?instance.eformEvAtom,
      'material': ?instance.material,
    };
