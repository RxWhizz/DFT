// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_chat_request.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentChatRequest _$AgentChatRequestFromJson(Map<String, dynamic> json) =>
    $checkedCreate('AgentChatRequest', json, ($checkedConvert) {
      $checkKeys(json, requiredKeys: const ['message']);
      final val = AgentChatRequest(
        message: $checkedConvert('message', (v) => v as String),
        history: $checkedConvert(
          'history',
          (v) => (v as List<dynamic>?)
              ?.map((e) => AgentMessage.fromJson(e as Map<String, dynamic>))
              .toList(),
        ),
        jobId: $checkedConvert('job_id', (v) => v as String?),
        structured: $checkedConvert('structured', (v) => v as bool?),
      );
      return val;
    }, fieldKeyMap: const {'jobId': 'job_id'});

Map<String, dynamic> _$AgentChatRequestToJson(AgentChatRequest instance) =>
    <String, dynamic>{
      'message': instance.message,
      'history': ?instance.history?.map((e) => e.toJson()).toList(),
      'job_id': ?instance.jobId,
      'structured': ?instance.structured,
    };
