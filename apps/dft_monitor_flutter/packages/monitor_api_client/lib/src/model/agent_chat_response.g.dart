// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_chat_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentChatResponse _$AgentChatResponseFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'AgentChatResponse',
      json,
      ($checkedConvert) {
        $checkKeys(
          json,
          requiredKeys: const [
            'ok',
            'model',
            'message',
            'tool_rounds',
            'tool_results',
          ],
        );
        final val = AgentChatResponse(
          ok: $checkedConvert('ok', (v) => v as bool),
          model: $checkedConvert('model', (v) => v as String),
          message: $checkedConvert('message', (v) => v as String),
          structured: $checkedConvert(
            'structured',
            (v) => (v as Map<String, dynamic>?)?.map(
              (k, e) => MapEntry(k, e as Object),
            ),
          ),
          toolRounds: $checkedConvert('tool_rounds', (v) => (v as num).toInt()),
          toolResults: $checkedConvert(
            'tool_results',
            (v) => (v as List<dynamic>)
                .map((e) => AgentToolResult.fromJson(e as Map<String, dynamic>))
                .toList(),
          ),
          proposalIds: $checkedConvert(
            'proposal_ids',
            (v) => (v as List<dynamic>?)?.map((e) => e as String).toList(),
          ),
        );
        return val;
      },
      fieldKeyMap: const {
        'toolRounds': 'tool_rounds',
        'toolResults': 'tool_results',
        'proposalIds': 'proposal_ids',
      },
    );

Map<String, dynamic> _$AgentChatResponseToJson(AgentChatResponse instance) =>
    <String, dynamic>{
      'ok': instance.ok,
      'model': instance.model,
      'message': instance.message,
      'structured': ?instance.structured,
      'tool_rounds': instance.toolRounds,
      'tool_results': instance.toolResults.map((e) => e.toJson()).toList(),
      'proposal_ids': ?instance.proposalIds,
    };
