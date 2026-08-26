//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'predict_request.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class PredictRequest {
  /// Returns a new [PredictRequest] instance.
  PredictRequest({

    required  this.A,

    required  this.B,

    required  this.X,

     this.aLat,

     this.eMaceEvAtom,

     this.bandGapGgaEv,

     this.eformEvAtom,

     this.material,
  });

  @JsonKey(
    
    name: r'A',
    required: true,
    includeIfNull: false,
  )


  final String A;



  @JsonKey(
    
    name: r'B',
    required: true,
    includeIfNull: false,
  )


  final String B;



  @JsonKey(
    
    name: r'X',
    required: true,
    includeIfNull: false,
  )


  final String X;



  @JsonKey(
    
    name: r'a_lat',
    required: false,
    includeIfNull: false,
  )


  final num? aLat;



  @JsonKey(
    
    name: r'e_mace_ev_atom',
    required: false,
    includeIfNull: false,
  )


  final num? eMaceEvAtom;



  @JsonKey(
    
    name: r'band_gap_gga_ev',
    required: false,
    includeIfNull: false,
  )


  final num? bandGapGgaEv;



  @JsonKey(
    
    name: r'eform_ev_atom',
    required: false,
    includeIfNull: false,
  )


  final num? eformEvAtom;



  @JsonKey(
    
    name: r'material',
    required: false,
    includeIfNull: false,
  )


  final String? material;





    @override
    bool operator ==(Object other) => identical(this, other) || other is PredictRequest &&
      other.A == A &&
      other.B == B &&
      other.X == X &&
      other.aLat == aLat &&
      other.eMaceEvAtom == eMaceEvAtom &&
      other.bandGapGgaEv == bandGapGgaEv &&
      other.eformEvAtom == eformEvAtom &&
      other.material == material;

    @override
    int get hashCode =>
        A.hashCode +
        B.hashCode +
        X.hashCode +
        (aLat == null ? 0 : aLat.hashCode) +
        (eMaceEvAtom == null ? 0 : eMaceEvAtom.hashCode) +
        (bandGapGgaEv == null ? 0 : bandGapGgaEv.hashCode) +
        (eformEvAtom == null ? 0 : eformEvAtom.hashCode) +
        (material == null ? 0 : material.hashCode);

  factory PredictRequest.fromJson(Map<String, dynamic> json) => _$PredictRequestFromJson(json);

  Map<String, dynamic> toJson() => _$PredictRequestToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

