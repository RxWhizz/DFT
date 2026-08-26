//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'agent_health_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AgentHealthResponse {
  /// Returns a new [AgentHealthResponse] instance.
  AgentHealthResponse({

    required  this.enabled,

    required  this.provider,

    required  this.ok,

    required  this.baseUrl,

    required  this.model,

     this.modelPresent,

    required  this.manageService,

     this.allowWrites,

    required  this.modelsDir,

    required  this.reviveRepo,

     this.version,

     this.error,
  });

  @JsonKey(
    
    name: r'enabled',
    required: true,
    includeIfNull: false,
  )


  final bool enabled;



  @JsonKey(
    
    name: r'provider',
    required: true,
    includeIfNull: false,
  )


  final String provider;



  @JsonKey(
    
    name: r'ok',
    required: true,
    includeIfNull: false,
  )


  final bool ok;



  @JsonKey(
    
    name: r'base_url',
    required: true,
    includeIfNull: false,
  )


  final String baseUrl;



  @JsonKey(
    
    name: r'model',
    required: true,
    includeIfNull: false,
  )


  final String model;



  @JsonKey(
    
    name: r'model_present',
    required: false,
    includeIfNull: false,
  )


  final bool? modelPresent;



  @JsonKey(
    
    name: r'manage_service',
    required: true,
    includeIfNull: false,
  )


  final bool manageService;



  @JsonKey(
    
    name: r'allow_writes',
    required: false,
    includeIfNull: false,
  )


  final bool? allowWrites;



  @JsonKey(
    
    name: r'models_dir',
    required: true,
    includeIfNull: false,
  )


  final String modelsDir;



  @JsonKey(
    
    name: r'revive_repo',
    required: true,
    includeIfNull: false,
  )


  final String reviveRepo;



  @JsonKey(
    
    name: r'version',
    required: false,
    includeIfNull: false,
  )


  final String? version;



  @JsonKey(
    
    name: r'error',
    required: false,
    includeIfNull: false,
  )


  final String? error;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AgentHealthResponse &&
      other.enabled == enabled &&
      other.provider == provider &&
      other.ok == ok &&
      other.baseUrl == baseUrl &&
      other.model == model &&
      other.modelPresent == modelPresent &&
      other.manageService == manageService &&
      other.allowWrites == allowWrites &&
      other.modelsDir == modelsDir &&
      other.reviveRepo == reviveRepo &&
      other.version == version &&
      other.error == error;

    @override
    int get hashCode =>
        enabled.hashCode +
        provider.hashCode +
        ok.hashCode +
        baseUrl.hashCode +
        model.hashCode +
        modelPresent.hashCode +
        manageService.hashCode +
        allowWrites.hashCode +
        modelsDir.hashCode +
        reviveRepo.hashCode +
        (version == null ? 0 : version.hashCode) +
        (error == null ? 0 : error.hashCode);

  factory AgentHealthResponse.fromJson(Map<String, dynamic> json) => _$AgentHealthResponseFromJson(json);

  Map<String, dynamic> toJson() => _$AgentHealthResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

