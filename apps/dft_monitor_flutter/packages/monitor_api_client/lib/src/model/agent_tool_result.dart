//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'agent_tool_result.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AgentToolResult {
  /// Returns a new [AgentToolResult] instance.
  AgentToolResult({

    required  this.name,

     this.arguments,

    required  this.ok,

     this.data,

     this.error,

     this.statusCode,
  });

  @JsonKey(
    
    name: r'name',
    required: true,
    includeIfNull: false,
  )


  final String name;



  @JsonKey(
    
    name: r'arguments',
    required: false,
    includeIfNull: false,
  )


  final Map<String, Object>? arguments;



  @JsonKey(
    
    name: r'ok',
    required: true,
    includeIfNull: false,
  )


  final bool ok;



  @JsonKey(
    
    name: r'data',
    required: false,
    includeIfNull: false,
  )


  final Map<String, Object>? data;



  @JsonKey(
    
    name: r'error',
    required: false,
    includeIfNull: false,
  )


  final String? error;



  @JsonKey(
    
    name: r'status_code',
    required: false,
    includeIfNull: false,
  )


  final int? statusCode;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AgentToolResult &&
      other.name == name &&
      other.arguments == arguments &&
      other.ok == ok &&
      other.data == data &&
      other.error == error &&
      other.statusCode == statusCode;

    @override
    int get hashCode =>
        name.hashCode +
        arguments.hashCode +
        ok.hashCode +
        (data == null ? 0 : data.hashCode) +
        (error == null ? 0 : error.hashCode) +
        (statusCode == null ? 0 : statusCode.hashCode);

  factory AgentToolResult.fromJson(Map<String, dynamic> json) => _$AgentToolResultFromJson(json);

  Map<String, dynamic> toJson() => _$AgentToolResultToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

