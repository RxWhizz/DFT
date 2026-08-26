//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'stats_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class StatsResponse {
  /// Returns a new [StatsResponse] instance.
  StatsResponse({

    required  this.jobId,

    required  this.formula,

    required  this.status,

     this.pid,

     this.startTime,

     this.elapsedMin,

     this.mpiCores,

     this.energyHistory,

     this.fmaxHistory,

     this.scfIterHistory,

     this.nFireSteps,

     this.nScfIters,

     this.isOscillating,

     this.stallMinutes,

     this.finalEnergyEv,
  });

  @JsonKey(
    
    name: r'job_id',
    required: true,
    includeIfNull: false,
  )


  final String jobId;



  @JsonKey(
    
    name: r'formula',
    required: true,
    includeIfNull: false,
  )


  final String formula;



  @JsonKey(
    
    name: r'status',
    required: true,
    includeIfNull: false,
  )


  final StatsResponseStatusEnum status;



  @JsonKey(
    
    name: r'pid',
    required: false,
    includeIfNull: false,
  )


  final int? pid;



  @JsonKey(
    
    name: r'start_time',
    required: false,
    includeIfNull: false,
  )


  final String? startTime;



  @JsonKey(
    
    name: r'elapsed_min',
    required: false,
    includeIfNull: false,
  )


  final num? elapsedMin;



  @JsonKey(
    
    name: r'mpi_cores',
    required: false,
    includeIfNull: false,
  )


  final int? mpiCores;



  @JsonKey(
    
    name: r'energy_history',
    required: false,
    includeIfNull: false,
  )


  final List<num>? energyHistory;



  @JsonKey(
    
    name: r'fmax_history',
    required: false,
    includeIfNull: false,
  )


  final List<num>? fmaxHistory;



  @JsonKey(
    
    name: r'scf_iter_history',
    required: false,
    includeIfNull: false,
  )


  final List<int>? scfIterHistory;



  @JsonKey(
    
    name: r'n_fire_steps',
    required: false,
    includeIfNull: false,
  )


  final int? nFireSteps;



  @JsonKey(
    
    name: r'n_scf_iters',
    required: false,
    includeIfNull: false,
  )


  final int? nScfIters;



  @JsonKey(
    
    name: r'is_oscillating',
    required: false,
    includeIfNull: false,
  )


  final bool? isOscillating;



  @JsonKey(
    
    name: r'stall_minutes',
    required: false,
    includeIfNull: false,
  )


  final num? stallMinutes;



  @JsonKey(
    
    name: r'final_energy_ev',
    required: false,
    includeIfNull: false,
  )


  final num? finalEnergyEv;





    @override
    bool operator ==(Object other) => identical(this, other) || other is StatsResponse &&
      other.jobId == jobId &&
      other.formula == formula &&
      other.status == status &&
      other.pid == pid &&
      other.startTime == startTime &&
      other.elapsedMin == elapsedMin &&
      other.mpiCores == mpiCores &&
      other.energyHistory == energyHistory &&
      other.fmaxHistory == fmaxHistory &&
      other.scfIterHistory == scfIterHistory &&
      other.nFireSteps == nFireSteps &&
      other.nScfIters == nScfIters &&
      other.isOscillating == isOscillating &&
      other.stallMinutes == stallMinutes &&
      other.finalEnergyEv == finalEnergyEv;

    @override
    int get hashCode =>
        jobId.hashCode +
        formula.hashCode +
        status.hashCode +
        (pid == null ? 0 : pid.hashCode) +
        (startTime == null ? 0 : startTime.hashCode) +
        (elapsedMin == null ? 0 : elapsedMin.hashCode) +
        (mpiCores == null ? 0 : mpiCores.hashCode) +
        energyHistory.hashCode +
        fmaxHistory.hashCode +
        scfIterHistory.hashCode +
        nFireSteps.hashCode +
        nScfIters.hashCode +
        isOscillating.hashCode +
        (stallMinutes == null ? 0 : stallMinutes.hashCode) +
        (finalEnergyEv == null ? 0 : finalEnergyEv.hashCode);

  factory StatsResponse.fromJson(Map<String, dynamic> json) => _$StatsResponseFromJson(json);

  Map<String, dynamic> toJson() => _$StatsResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}


enum StatsResponseStatusEnum {
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

const StatsResponseStatusEnum(this.value);

final String value;

@override
String toString() => value;
}


