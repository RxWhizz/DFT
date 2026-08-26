// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_proposal_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentProposalResponse _$AgentProposalResponseFromJson(
  Map<String, dynamic> json,
) => $checkedCreate('AgentProposalResponse', json, ($checkedConvert) {
  $checkKeys(json, requiredKeys: const ['id', 'title', 'created_at', 'status']);
  final val = AgentProposalResponse(
    id: $checkedConvert('id', (v) => v as String),
    title: $checkedConvert('title', (v) => v as String),
    createdAt: $checkedConvert('created_at', (v) => v as num),
    status: $checkedConvert('status', (v) => v as String),
    command: $checkedConvert('command', (v) => v as String?),
    diff: $checkedConvert('diff', (v) => v as String?),
    rationale: $checkedConvert('rationale', (v) => v as String?),
    metadata: $checkedConvert(
      'metadata',
      (v) =>
          (v as Map<String, dynamic>?)?.map((k, e) => MapEntry(k, e as Object)),
    ),
    executed: $checkedConvert('executed', (v) => v as bool?),
  );
  return val;
}, fieldKeyMap: const {'createdAt': 'created_at'});

Map<String, dynamic> _$AgentProposalResponseToJson(
  AgentProposalResponse instance,
) => <String, dynamic>{
  'id': instance.id,
  'title': instance.title,
  'created_at': instance.createdAt,
  'status': instance.status,
  'command': ?instance.command,
  'diff': ?instance.diff,
  'rationale': ?instance.rationale,
  'metadata': ?instance.metadata,
  'executed': ?instance.executed,
};
