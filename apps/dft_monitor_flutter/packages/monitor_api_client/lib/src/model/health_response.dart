//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:monitor_api_client/src/model/platform_info.dart';
import 'package:monitor_api_client/src/model/paths_info.dart';
import 'package:json_annotation/json_annotation.dart';

part 'health_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class HealthResponse {
  /// Returns a new [HealthResponse] instance.
  HealthResponse({

    required  this.ok,

    required  this.version,

    required  this.paths,

    required  this.platform,

    required  this.runsDir,

    required  this.runsMounted,

    required  this.nearestExistingPath,

    required  this.nJobsTracked,

    required  this.lastPollAt,

    required  this.lastPollAgeSec,

    required  this.pollIntervalSec,

    required  this.wsClients,
  });

  @JsonKey(
    
    name: r'ok',
    required: true,
    includeIfNull: false,
  )


  final bool ok;



  @JsonKey(
    
    name: r'version',
    required: true,
    includeIfNull: false,
  )


  final String version;



  @JsonKey(
    
    name: r'paths',
    required: true,
    includeIfNull: false,
  )


  final PathsInfo paths;



  @JsonKey(
    
    name: r'platform',
    required: true,
    includeIfNull: false,
  )


  final PlatformInfo platform;



  @JsonKey(
    
    name: r'runs_dir',
    required: true,
    includeIfNull: false,
  )


  final String runsDir;



  @JsonKey(
    
    name: r'runs_mounted',
    required: true,
    includeIfNull: false,
  )


  final bool runsMounted;



  @JsonKey(
    
    name: r'nearest_existing_path',
    required: true,
    includeIfNull: false,
  )


  final String nearestExistingPath;



  @JsonKey(
    
    name: r'n_jobs_tracked',
    required: true,
    includeIfNull: false,
  )


  final int nJobsTracked;



  @JsonKey(
    
    name: r'last_poll_at',
    required: true,
    includeIfNull: true,
  )


  final num? lastPollAt;



  @JsonKey(
    
    name: r'last_poll_age_sec',
    required: true,
    includeIfNull: true,
  )


  final num? lastPollAgeSec;



  @JsonKey(
    
    name: r'poll_interval_sec',
    required: true,
    includeIfNull: false,
  )


  final int pollIntervalSec;



  @JsonKey(
    
    name: r'ws_clients',
    required: true,
    includeIfNull: false,
  )


  final int wsClients;





    @override
    bool operator ==(Object other) => identical(this, other) || other is HealthResponse &&
      other.ok == ok &&
      other.version == version &&
      other.paths == paths &&
      other.platform == platform &&
      other.runsDir == runsDir &&
      other.runsMounted == runsMounted &&
      other.nearestExistingPath == nearestExistingPath &&
      other.nJobsTracked == nJobsTracked &&
      other.lastPollAt == lastPollAt &&
      other.lastPollAgeSec == lastPollAgeSec &&
      other.pollIntervalSec == pollIntervalSec &&
      other.wsClients == wsClients;

    @override
    int get hashCode =>
        ok.hashCode +
        version.hashCode +
        paths.hashCode +
        platform.hashCode +
        runsDir.hashCode +
        runsMounted.hashCode +
        nearestExistingPath.hashCode +
        nJobsTracked.hashCode +
        (lastPollAt == null ? 0 : lastPollAt.hashCode) +
        (lastPollAgeSec == null ? 0 : lastPollAgeSec.hashCode) +
        pollIntervalSec.hashCode +
        wsClients.hashCode;

  factory HealthResponse.fromJson(Map<String, dynamic> json) => _$HealthResponseFromJson(json);

  Map<String, dynamic> toJson() => _$HealthResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

