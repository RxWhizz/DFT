// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_tool_result.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentToolResult _$AgentToolResultFromJson(
  Map<String, dynamic> json,
) => $checkedCreate('AgentToolResult', json, ($checkedConvert) {
  $checkKeys(json, requiredKeys: const ['name', 'ok']);
  final val = AgentToolResult(
    name: $checkedConvert('name', (v) => v as String),
    arguments: $checkedConvert(
      'arguments',
      (v) =>
          (v as Map<String, dynamic>?)?.map((k, e) => MapEntry(k, e as Object)),
    ),
    ok: $checkedConvert('ok', (v) => v as bool),
    data: $checkedConvert(
      'data',
      (v) =>
          (v as Map<String, dynamic>?)?.map((k, e) => MapEntry(k, e as Object)),
    ),
    error: $checkedConvert('error', (v) => v as String?),
    statusCode: $checkedConvert('status_code', (v) => (v as num?)?.toInt()),
  );
  return val;
}, fieldKeyMap: const {'statusCode': 'status_code'});

Map<String, dynamic> _$AgentToolResultToJson(AgentToolResult instance) =>
    <String, dynamic>{
      'name': instance.name,
      'arguments': ?instance.arguments,
      'ok': instance.ok,
      'data': ?instance.data,
      'error': ?instance.error,
      'status_code': ?instance.statusCode,
    };
