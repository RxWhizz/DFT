//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'sys_metrics_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class SysMetricsResponse {
  /// Returns a new [SysMetricsResponse] instance.
  SysMetricsResponse({

    required  this.cpuPercent,

    required  this.cpuPerCore,

    required  this.ramUsedGb,

    required  this.ramTotalGb,

    required  this.ramPercent,

    required  this.pkgTemps,

    required  this.coreTempMax,

    required  this.nvmeTemp,

    required  this.gpuTemps,
  });

  @JsonKey(
    
    name: r'cpu_percent',
    required: true,
    includeIfNull: false,
  )


  final num cpuPercent;



  @JsonKey(
    
    name: r'cpu_per_core',
    required: true,
    includeIfNull: false,
  )


  final List<num> cpuPerCore;



  @JsonKey(
    
    name: r'ram_used_gb',
    required: true,
    includeIfNull: false,
  )


  final num ramUsedGb;



  @JsonKey(
    
    name: r'ram_total_gb',
    required: true,
    includeIfNull: false,
  )


  final num ramTotalGb;



  @JsonKey(
    
    name: r'ram_percent',
    required: true,
    includeIfNull: false,
  )


  final num ramPercent;



  @JsonKey(
    
    name: r'pkg_temps',
    required: true,
    includeIfNull: false,
  )


  final List<num> pkgTemps;



  @JsonKey(
    
    name: r'core_temp_max',
    required: true,
    includeIfNull: false,
  )


  final num coreTempMax;



  @JsonKey(
    
    name: r'nvme_temp',
    required: true,
    includeIfNull: true,
  )


  final num? nvmeTemp;



  @JsonKey(
    
    name: r'gpu_temps',
    required: true,
    includeIfNull: false,
  )


  final List<num> gpuTemps;





    @override
    bool operator ==(Object other) => identical(this, other) || other is SysMetricsResponse &&
      other.cpuPercent == cpuPercent &&
      other.cpuPerCore == cpuPerCore &&
      other.ramUsedGb == ramUsedGb &&
      other.ramTotalGb == ramTotalGb &&
      other.ramPercent == ramPercent &&
      other.pkgTemps == pkgTemps &&
      other.coreTempMax == coreTempMax &&
      other.nvmeTemp == nvmeTemp &&
      other.gpuTemps == gpuTemps;

    @override
    int get hashCode =>
        cpuPercent.hashCode +
        cpuPerCore.hashCode +
        ramUsedGb.hashCode +
        ramTotalGb.hashCode +
        ramPercent.hashCode +
        pkgTemps.hashCode +
        coreTempMax.hashCode +
        (nvmeTemp == null ? 0 : nvmeTemp.hashCode) +
        gpuTemps.hashCode;

  factory SysMetricsResponse.fromJson(Map<String, dynamic> json) => _$SysMetricsResponseFromJson(json);

  Map<String, dynamic> toJson() => _$SysMetricsResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

