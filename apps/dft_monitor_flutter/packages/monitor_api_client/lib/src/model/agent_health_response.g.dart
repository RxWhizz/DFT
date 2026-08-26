// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'agent_health_response.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AgentHealthResponse _$AgentHealthResponseFromJson(Map<String, dynamic> json) =>
    $checkedCreate(
      'AgentHealthResponse',
      json,
      ($checkedConvert) {
        $checkKeys(
          json,
          requiredKeys: const [
            'enabled',
            'provider',
            'ok',
            'base_url',
            'model',
            'manage_service',
            'models_dir',
            'revive_repo',
          ],
        );
        final val = AgentHealthResponse(
          enabled: $checkedConvert('enabled', (v) => v as bool),
          provider: $checkedConvert('provider', (v) => v as String),
          ok: $checkedConvert('ok', (v) => v as bool),
          baseUrl: $checkedConvert('base_url', (v) => v as String),
          model: $checkedConvert('model', (v) => v as String),
          modelPresent: $checkedConvert('model_present', (v) => v as bool?),
          manageService: $checkedConvert('manage_service', (v) => v as bool),
          allowWrites: $checkedConvert('allow_writes', (v) => v as bool?),
          modelsDir: $checkedConvert('models_dir', (v) => v as String),
          reviveRepo: $checkedConvert('revive_repo', (v) => v as String),
          version: $checkedConvert('version', (v) => v as String?),
          error: $checkedConvert('error', (v) => v as String?),
        );
        return val;
      },
      fieldKeyMap: const {
        'baseUrl': 'base_url',
        'modelPresent': 'model_present',
        'manageService': 'manage_service',
        'allowWrites': 'allow_writes',
        'modelsDir': 'models_dir',
        'reviveRepo': 'revive_repo',
      },
    );

Map<String, dynamic> _$AgentHealthResponseToJson(
  AgentHealthResponse instance,
) => <String, dynamic>{
  'enabled': instance.enabled,
  'provider': instance.provider,
  'ok': instance.ok,
  'base_url': instance.baseUrl,
  'model': instance.model,
  'model_present': ?instance.modelPresent,
  'manage_service': instance.manageService,
  'allow_writes': ?instance.allowWrites,
  'models_dir': instance.modelsDir,
  'revive_repo': instance.reviveRepo,
  'version': ?instance.version,
  'error': ?instance.error,
};
