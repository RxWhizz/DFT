//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'summary_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class SummaryResponse {
  /// Returns a new [SummaryResponse] instance.
  SummaryResponse({

    required  this.nPending,

    required  this.nRunning,

    required  this.nConverged,

    required  this.nFailed,

    required  this.nStalled,

    required  this.nOscillating,

     this.nSkippedDuplicate,

    required  this.total,

     this.convergenceRate,
  });

  @JsonKey(
    
    name: r'n_pending',
    required: true,
    includeIfNull: false,
  )


  final int nPending;



  @JsonKey(
    
    name: r'n_running',
    required: true,
    includeIfNull: false,
  )


  final int nRunning;



  @JsonKey(
    
    name: r'n_converged',
    required: true,
    includeIfNull: false,
  )


  final int nConverged;



  @JsonKey(
    
    name: r'n_failed',
    required: true,
    includeIfNull: false,
  )


  final int nFailed;



  @JsonKey(
    
    name: r'n_stalled',
    required: true,
    includeIfNull: false,
  )


  final int nStalled;



  @JsonKey(
    
    name: r'n_oscillating',
    required: true,
    includeIfNull: false,
  )


  final int nOscillating;



  @JsonKey(
    
    name: r'n_skipped_duplicate',
    required: false,
    includeIfNull: false,
  )


  final int? nSkippedDuplicate;



  @JsonKey(
    
    name: r'total',
    required: true,
    includeIfNull: false,
  )


  final int total;



  @JsonKey(
    
    name: r'convergence_rate',
    required: false,
    includeIfNull: false,
  )


  final num? convergenceRate;





    @override
    bool operator ==(Object other) => identical(this, other) || other is SummaryResponse &&
      other.nPending == nPending &&
      other.nRunning == nRunning &&
      other.nConverged == nConverged &&
      other.nFailed == nFailed &&
      other.nStalled == nStalled &&
      other.nOscillating == nOscillating &&
      other.nSkippedDuplicate == nSkippedDuplicate &&
      other.total == total &&
      other.convergenceRate == convergenceRate;

    @override
    int get hashCode =>
        nPending.hashCode +
        nRunning.hashCode +
        nConverged.hashCode +
        nFailed.hashCode +
        nStalled.hashCode +
        nOscillating.hashCode +
        nSkippedDuplicate.hashCode +
        total.hashCode +
        (convergenceRate == null ? 0 : convergenceRate.hashCode);

  factory SummaryResponse.fromJson(Map<String, dynamic> json) => _$SummaryResponseFromJson(json);

  Map<String, dynamic> toJson() => _$SummaryResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

