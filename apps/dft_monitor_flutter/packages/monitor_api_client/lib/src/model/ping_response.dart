//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'ping_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class PingResponse {
  /// Returns a new [PingResponse] instance.
  PingResponse({

    required  this.jobId,

    required  this.alive,

     this.currentStep,

     this.stepType,

     this.energyEv,

     this.fmaxEvAng,

     this.memoryRssMb,

     this.tIterS,

     this.etaMin,

     this.logLastLine,

     this.status,
  });

  @JsonKey(
    
    name: r'job_id',
    required: true,
    includeIfNull: false,
  )


  final String jobId;



  @JsonKey(
    
    name: r'alive',
    required: true,
    includeIfNull: false,
  )


  final bool alive;



  @JsonKey(
    
    name: r'current_step',
    required: false,
    includeIfNull: false,
  )


  final int? currentStep;



  @JsonKey(
    
    name: r'step_type',
    required: false,
    includeIfNull: false,
  )


  final String? stepType;



  @JsonKey(
    
    name: r'energy_ev',
    required: false,
    includeIfNull: false,
  )


  final num? energyEv;



  @JsonKey(
    
    name: r'fmax_ev_ang',
    required: false,
    includeIfNull: false,
  )


  final num? fmaxEvAng;



  @JsonKey(
    
    name: r'memory_rss_mb',
    required: false,
    includeIfNull: false,
  )


  final int? memoryRssMb;



  @JsonKey(
    
    name: r't_iter_s',
    required: false,
    includeIfNull: false,
  )


  final num? tIterS;



  @JsonKey(
    
    name: r'eta_min',
    required: false,
    includeIfNull: false,
  )


  final num? etaMin;



  @JsonKey(
    
    name: r'log_last_line',
    required: false,
    includeIfNull: false,
  )


  final String? logLastLine;



  @JsonKey(
    
    name: r'status',
    required: false,
    includeIfNull: false,
  )


  final PingResponseStatusEnum? status;





    @override
    bool operator ==(Object other) => identical(this, other) || other is PingResponse &&
      other.jobId == jobId &&
      other.alive == alive &&
      other.currentStep == currentStep &&
      other.stepType == stepType &&
      other.energyEv == energyEv &&
      other.fmaxEvAng == fmaxEvAng &&
      other.memoryRssMb == memoryRssMb &&
      other.tIterS == tIterS &&
      other.etaMin == etaMin &&
      other.logLastLine == logLastLine &&
      other.status == status;

    @override
    int get hashCode =>
        jobId.hashCode +
        alive.hashCode +
        (currentStep == null ? 0 : currentStep.hashCode) +
        (stepType == null ? 0 : stepType.hashCode) +
        (energyEv == null ? 0 : energyEv.hashCode) +
        (fmaxEvAng == null ? 0 : fmaxEvAng.hashCode) +
        (memoryRssMb == null ? 0 : memoryRssMb.hashCode) +
        (tIterS == null ? 0 : tIterS.hashCode) +
        (etaMin == null ? 0 : etaMin.hashCode) +
        (logLastLine == null ? 0 : logLastLine.hashCode) +
        status.hashCode;

  factory PingResponse.fromJson(Map<String, dynamic> json) => _$PingResponseFromJson(json);

  Map<String, dynamic> toJson() => _$PingResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}


enum PingResponseStatusEnum {
@JsonValue(r'pending')
pending(r'pending'),
@JsonValue(r'running')
running(r'running'),
@JsonValue(r'converged')
converged(r'converged'),
@JsonValue(r'partial')
partial(r'partial'),
@JsonValue(r'failed')
failed(r'failed'),
@JsonValue(r'stalled')
stalled(r'stalled'),
@JsonValue(r'oscillating')
oscillating(r'oscillating'),
@JsonValue(r'stopped')
stopped(r'stopped'),
@JsonValue(r'skipped_duplicate')
skippedDuplicate(r'skipped_duplicate'),
@JsonValue(r'unknown')
unknown(r'unknown');

const PingResponseStatusEnum(this.value);

final String value;

@override
String toString() => value;
}


