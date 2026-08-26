//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:monitor_api_client/src/model/agent_message.dart';
import 'package:json_annotation/json_annotation.dart';

part 'agent_chat_request.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AgentChatRequest {
  /// Returns a new [AgentChatRequest] instance.
  AgentChatRequest({

    required  this.message,

     this.history,

     this.jobId,

     this.structured,
  });

  @JsonKey(
    
    name: r'message',
    required: true,
    includeIfNull: false,
  )


  final String message;



  @JsonKey(
    
    name: r'history',
    required: false,
    includeIfNull: false,
  )


  final List<AgentMessage>? history;



  @JsonKey(
    
    name: r'job_id',
    required: false,
    includeIfNull: false,
  )


  final String? jobId;



  @JsonKey(
    
    name: r'structured',
    required: false,
    includeIfNull: false,
  )


  final bool? structured;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AgentChatRequest &&
      other.message == message &&
      other.history == history &&
      other.jobId == jobId &&
      other.structured == structured;

    @override
    int get hashCode =>
        message.hashCode +
        history.hashCode +
        (jobId == null ? 0 : jobId.hashCode) +
        structured.hashCode;

  factory AgentChatRequest.fromJson(Map<String, dynamic> json) => _$AgentChatRequestFromJson(json);

  Map<String, dynamic> toJson() => _$AgentChatRequestToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

