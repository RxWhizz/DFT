//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'job_status.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class JobStatus {
  /// Returns a new [JobStatus] instance.
  JobStatus({

    required  this.jobId,

    required  this.formula,

    required  this.status,

     this.pid,

     this.startTime,

     this.elapsedMin,

     this.mpiCores,
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


  final JobStatusStatusEnum status;



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





    @override
    bool operator ==(Object other) => identical(this, other) || other is JobStatus &&
      other.jobId == jobId &&
      other.formula == formula &&
      other.status == status &&
      other.pid == pid &&
      other.startTime == startTime &&
      other.elapsedMin == elapsedMin &&
      other.mpiCores == mpiCores;

    @override
    int get hashCode =>
        jobId.hashCode +
        formula.hashCode +
        status.hashCode +
        (pid == null ? 0 : pid.hashCode) +
        (startTime == null ? 0 : startTime.hashCode) +
        (elapsedMin == null ? 0 : elapsedMin.hashCode) +
        (mpiCores == null ? 0 : mpiCores.hashCode);

  factory JobStatus.fromJson(Map<String, dynamic> json) => _$JobStatusFromJson(json);

  Map<String, dynamic> toJson() => _$JobStatusToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}


enum JobStatusStatusEnum {
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

const JobStatusStatusEnum(this.value);

final String value;

@override
String toString() => value;
}


