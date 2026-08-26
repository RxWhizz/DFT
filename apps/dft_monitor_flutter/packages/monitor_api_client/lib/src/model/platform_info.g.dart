// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'platform_info.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PlatformInfo _$PlatformInfoFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'PlatformInfo',
      json,
      ($checkedConvert) {
        $checkKeys(
          json,
          requiredKeys: const [
            'os',
            'frozen',
            'hardware_temps',
            'runner_launch',
          ],
        );
        final val = PlatformInfo(
          os: $checkedConvert('os', (v) => v as String),
          frozen: $checkedConvert('frozen', (v) => v as bool),
          hardwareTemps: $checkedConvert('hardware_temps', (v) => v as bool),
          runnerLaunch: $checkedConvert('runner_launch', (v) => v as bool),
          runnerPython: $checkedConvert('runner_python', (v) => v as String?),
          autoAdvance: $checkedConvert('auto_advance', (v) => v as bool?),
        );
        return val;
      },
      fieldKeyMap: const {
        'hardwareTemps': 'hardware_temps',
        'runnerLaunch': 'runner_launch',
        'runnerPython': 'runner_python',
        'autoAdvance': 'auto_advance',
      },
    );

Map<String, dynamic> _$PlatformInfoToJson(PlatformInfo instance) =>
    <String, dynamic>{
      'os': instance.os,
      'frozen': instance.frozen,
      'hardware_temps': instance.hardwareTemps,
      'runner_launch': instance.runnerLaunch,
      'runner_python': ?instance.runnerPython,
      'auto_advance': ?instance.autoAdvance,
    };
