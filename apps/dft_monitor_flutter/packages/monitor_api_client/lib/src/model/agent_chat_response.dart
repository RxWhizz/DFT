//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:monitor_api_client/src/model/agent_tool_result.dart';
import 'package:json_annotation/json_annotation.dart';

part 'agent_chat_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AgentChatResponse {
  /// Returns a new [AgentChatResponse] instance.
  AgentChatResponse({

    required  this.ok,

    required  this.model,

    required  this.message,

     this.structured,

    required  this.toolRounds,

    required  this.toolResults,

     this.proposalIds,
  });

  @JsonKey(
    
    name: r'ok',
    required: true,
    includeIfNull: false,
  )


  final bool ok;



  @JsonKey(
    
    name: r'model',
    required: true,
    includeIfNull: false,
  )


  final String model;



  @JsonKey(
    
    name: r'message',
    required: true,
    includeIfNull: false,
  )


  final String message;



  @JsonKey(
    
    name: r'structured',
    required: false,
    includeIfNull: false,
  )


  final Map<String, Object>? structured;



  @JsonKey(
    
    name: r'tool_rounds',
    required: true,
    includeIfNull: false,
  )


  final int toolRounds;



  @JsonKey(
    
    name: r'tool_results',
    required: true,
    includeIfNull: false,
  )


  final List<AgentToolResult> toolResults;



  @JsonKey(
    
    name: r'proposal_ids',
    required: false,
    includeIfNull: false,
  )


  final List<String>? proposalIds;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AgentChatResponse &&
      other.ok == ok &&
      other.model == model &&
      other.message == message &&
      other.structured == structured &&
      other.toolRounds == toolRounds &&
      other.toolResults == toolResults &&
      other.proposalIds == proposalIds;

    @override
    int get hashCode =>
        ok.hashCode +
        model.hashCode +
        message.hashCode +
        (structured == null ? 0 : structured.hashCode) +
        toolRounds.hashCode +
        toolResults.hashCode +
        proposalIds.hashCode;

  factory AgentChatResponse.fromJson(Map<String, dynamic> json) => _$AgentChatResponseFromJson(json);

  Map<String, dynamic> toJson() => _$AgentChatResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

