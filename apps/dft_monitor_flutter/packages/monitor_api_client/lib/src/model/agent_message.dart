//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'agent_message.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AgentMessage {
  /// Returns a new [AgentMessage] instance.
  AgentMessage({

    required  this.role,

    required  this.content,
  });

  @JsonKey(
    
    name: r'role',
    required: true,
    includeIfNull: false,
  )


  final AgentMessageRoleEnum role;



  @JsonKey(
    
    name: r'content',
    required: true,
    includeIfNull: false,
  )


  final String content;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AgentMessage &&
      other.role == role &&
      other.content == content;

    @override
    int get hashCode =>
        role.hashCode +
        content.hashCode;

  factory AgentMessage.fromJson(Map<String, dynamic> json) => _$AgentMessageFromJson(json);

  Map<String, dynamic> toJson() => _$AgentMessageToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}


enum AgentMessageRoleEnum {
@JsonValue(r'system')
system(r'system'),
@JsonValue(r'user')
user(r'user'),
@JsonValue(r'assistant')
assistant(r'assistant'),
@JsonValue(r'tool')
tool(r'tool');

const AgentMessageRoleEnum(this.value);

final String value;

@override
String toString() => value;
}


