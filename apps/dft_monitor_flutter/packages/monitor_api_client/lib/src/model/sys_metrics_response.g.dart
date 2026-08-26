// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'sys_metrics_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

SysMetricsResponse _$SysMetricsResponseFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'SysMetricsResponse',
      json,
      ($checkedConvert) {
        $checkKeys(
          json,
          requiredKeys: const [
            'cpu_percent',
            'cpu_per_core',
            'ram_used_gb',
            'ram_total_gb',
            'ram_percent',
            'pkg_temps',
            'core_temp_max',
            'nvme_temp',
            'gpu_temps',
          ],
        );
        final val = SysMetricsResponse(
          cpuPercent: $checkedConvert('cpu_percent', (v) => v as num),
          cpuPerCore: $checkedConvert(
            'cpu_per_core',
            (v) => (v as List<dynamic>).map((e) => e as num).toList(),
          ),
          ramUsedGb: $checkedConvert('ram_used_gb', (v) => v as num),
          ramTotalGb: $checkedConvert('ram_total_gb', (v) => v as num),
          ramPercent: $checkedConvert('ram_percent', (v) => v as num),
          pkgTemps: $checkedConvert(
            'pkg_temps',
            (v) => (v as List<dynamic>).map((e) => e as num).toList(),
          ),
          coreTempMax: $checkedConvert('core_temp_max', (v) => v as num),
          nvmeTemp: $checkedConvert('nvme_temp', (v) => v as num?),
          gpuTemps: $checkedConvert(
            'gpu_temps',
            (v) => (v as List<dynamic>).map((e) => e as num).toList(),
          ),
        );
        return val;
      },
      fieldKeyMap: const {
        'cpuPercent': 'cpu_percent',
        'cpuPerCore': 'cpu_per_core',
        'ramUsedGb': 'ram_used_gb',
        'ramTotalGb': 'ram_total_gb',
        'ramPercent': 'ram_percent',
        'pkgTemps': 'pkg_temps',
        'coreTempMax': 'core_temp_max',
        'nvmeTemp': 'nvme_temp',
        'gpuTemps': 'gpu_temps',
      },
    );

Map<String, dynamic> _$SysMetricsResponseToJson(SysMetricsResponse instance) =>
    <String, dynamic>{
      'cpu_percent': instance.cpuPercent,
      'cpu_per_core': instance.cpuPerCore,
      'ram_used_gb': instance.ramUsedGb,
      'ram_total_gb': instance.ramTotalGb,
      'ram_percent': instance.ramPercent,
      'pkg_temps': instance.pkgTemps,
      'core_temp_max': instance.coreTempMax,
      'nvme_temp': instance.nvmeTemp,
      'gpu_temps': instance.gpuTemps,
    };
