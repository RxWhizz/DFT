// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'health_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

HealthResponse _$HealthResponseFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'HealthResponse',
      json,
      ($checkedConvert) {
        $checkKeys(
          json,
          requiredKeys: const [
            'ok',
            'version',
            'paths',
            'platform',
            'runs_dir',
            'runs_mounted',
            'nearest_existing_path',
            'n_jobs_tracked',
            'last_poll_at',
            'last_poll_age_sec',
            'poll_interval_sec',
            'ws_clients',
          ],
        );
        final val = HealthResponse(
          ok: $checkedConvert('ok', (v) => v as bool),
          version: $checkedConvert('version', (v) => v as String),
          paths: $checkedConvert(
            'paths',
            (v) => PathsInfo.fromJson(v as Map<String, dynamic>),
          ),
          platform: $checkedConvert(
            'platform',
            (v) => PlatformInfo.fromJson(v as Map<String, dynamic>),
          ),
          runsDir: $checkedConvert('runs_dir', (v) => v as String),
          runsMounted: $checkedConvert('runs_mounted', (v) => v as bool),
          nearestExistingPath: $checkedConvert(
            'nearest_existing_path',
            (v) => v as String,
          ),
          nJobsTracked: $checkedConvert(
            'n_jobs_tracked',
            (v) => (v as num).toInt(),
          ),
          lastPollAt: $checkedConvert('last_poll_at', (v) => v as num?),
          lastPollAgeSec: $checkedConvert(
            'last_poll_age_sec',
            (v) => v as num?,
          ),
          pollIntervalSec: $checkedConvert(
            'poll_interval_sec',
            (v) => (v as num).toInt(),
          ),
          wsClients: $checkedConvert('ws_clients', (v) => (v as num).toInt()),
        );
        return val;
      },
      fieldKeyMap: const {
        'runsDir': 'runs_dir',
        'runsMounted': 'runs_mounted',
        'nearestExistingPath': 'nearest_existing_path',
        'nJobsTracked': 'n_jobs_tracked',
        'lastPollAt': 'last_poll_at',
        'lastPollAgeSec': 'last_poll_age_sec',
        'pollIntervalSec': 'poll_interval_sec',
        'wsClients': 'ws_clients',
      },
    );

Map<String, dynamic> _$HealthResponseToJson(HealthResponse instance) =>
    <String, dynamic>{
      'ok': instance.ok,
      'version': instance.version,
      'paths': instance.paths.toJson(),
      'platform': instance.platform.toJson(),
      'runs_dir': instance.runsDir,
      'runs_mounted': instance.runsMounted,
      'nearest_existing_path': instance.nearestExistingPath,
      'n_jobs_tracked': instance.nJobsTracked,
      'last_poll_at': instance.lastPollAt,
      'last_poll_age_sec': instance.lastPollAgeSec,
      'poll_interval_sec': instance.pollIntervalSec,
      'ws_clients': instance.wsClients,
    };
