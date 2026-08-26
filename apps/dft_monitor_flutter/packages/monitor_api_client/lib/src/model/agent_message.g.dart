// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_message.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentMessage _$AgentMessageFromJson(Map<String, dynamic> json) =>
    $checkedCreate('AgentMessage', json, ($checkedConvert) {
      $checkKeys(json, requiredKeys: const ['role', 'content']);
      final val = AgentMessage(
        role: $checkedConvert(
          'role',
          (v) => $enumDecode(_$AgentMessageRoleEnumEnumMap, v),
        ),
        content: $checkedConvert('content', (v) => v as String),
      );
      return val;
    });

Map<String, dynamic> _$AgentMessageToJson(AgentMessage instance) =>
    <String, dynamic>{
      'role': _$AgentMessageRoleEnumEnumMap[instance.role]!,
      'content': instance.content,
    };

const _$AgentMessageRoleEnumEnumMap = {
  AgentMessageRoleEnum.system: 'system',
  AgentMessageRoleEnum.user: 'user',
  AgentMessageRoleEnum.assistant: 'assistant',
  AgentMessageRoleEnum.tool: 'tool',
};
