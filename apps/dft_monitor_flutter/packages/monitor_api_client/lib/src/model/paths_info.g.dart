// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'paths_info.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

PathsInfo _$PathsInfoFromJson(Map<String, dynamic> json) => $checkedCreate(
  'PathsInfo',
  json,
  ($checkedConvert) {
    $checkKeys(
      json,
      requiredKeys: const ['frozen', 'bundle_root', 'data_root', 'config_dir'],
    );
    final val = PathsInfo(
      frozen: $checkedConvert('frozen', (v) => v as bool),
      bundleRoot: $checkedConvert('bundle_root', (v) => v as String),
      dataRoot: $checkedConvert('data_root', (v) => v as String),
      configDir: $checkedConvert('config_dir', (v) => v as String),
    );
    return val;
  },
  fieldKeyMap: const {
    'bundleRoot': 'bundle_root',
    'dataRoot': 'data_root',
    'configDir': 'config_dir',
  },
);

Map<String, dynamic> _$PathsInfoToJson(PathsInfo instance) => <String, dynamic>{
  'frozen': instance.frozen,
  'bundle_root': instance.bundleRoot,
  'data_root': instance.dataRoot,
  'config_dir': instance.configDir,
};
