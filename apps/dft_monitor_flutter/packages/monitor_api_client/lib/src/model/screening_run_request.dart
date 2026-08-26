//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'screening_run_request.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class ScreeningRunRequest {
  /// Returns a new [ScreeningRunRequest] instance.
  ScreeningRunRequest({

     this.batchId,

     this.nCandidates,

     this.nBatches,

     this.randomSeed,

     this.useMlff,
  });

  @JsonKey(
    
    name: r'batch_id',
    required: false,
    includeIfNull: false,
  )


  final int? batchId;



  @JsonKey(
    
    name: r'n_candidates',
    required: false,
    includeIfNull: false,
  )


  final int? nCandidates;



  @JsonKey(
    
    name: r'n_batches',
    required: false,
    includeIfNull: false,
  )


  final int? nBatches;



  @JsonKey(
    
    name: r'random_seed',
    required: false,
    includeIfNull: false,
  )


  final int? randomSeed;



  @JsonKey(
    
    name: r'use_mlff',
    required: false,
    includeIfNull: false,
  )


  final bool? useMlff;





    @override
    bool operator ==(Object other) => identical(this, other) || other is ScreeningRunRequest &&
      other.batchId == batchId &&
      other.nCandidates == nCandidates &&
      other.nBatches == nBatches &&
      other.randomSeed == randomSeed &&
      other.useMlff == useMlff;

    @override
    int get hashCode =>
        (batchId == null ? 0 : batchId.hashCode) +
        nCandidates.hashCode +
        nBatches.hashCode +
        (randomSeed == null ? 0 : randomSeed.hashCode) +
        (useMlff == null ? 0 : useMlff.hashCode);

  factory ScreeningRunRequest.fromJson(Map<String, dynamic> json) => _$ScreeningRunRequestFromJson(json);

  Map<String, dynamic> toJson() => _$ScreeningRunRequestToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

