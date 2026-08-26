//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'agent_proposal_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AgentProposalResponse {
  /// Returns a new [AgentProposalResponse] instance.
  AgentProposalResponse({

    required  this.id,

    required  this.title,

    required  this.createdAt,

    required  this.status,

     this.command,

     this.diff,

     this.rationale,

     this.metadata,

     this.executed,
  });

  @JsonKey(
    
    name: r'id',
    required: true,
    includeIfNull: false,
  )


  final String id;



  @JsonKey(
    
    name: r'title',
    required: true,
    includeIfNull: false,
  )


  final String title;



  @JsonKey(
    
    name: r'created_at',
    required: true,
    includeIfNull: false,
  )


  final num createdAt;



  @JsonKey(
    
    name: r'status',
    required: true,
    includeIfNull: false,
  )


  final String status;



  @JsonKey(
    
    name: r'command',
    required: false,
    includeIfNull: false,
  )


  final String? command;



  @JsonKey(
    
    name: r'diff',
    required: false,
    includeIfNull: false,
  )


  final String? diff;



  @JsonKey(
    
    name: r'rationale',
    required: false,
    includeIfNull: false,
  )


  final String? rationale;



  @JsonKey(
    
    name: r'metadata',
    required: false,
    includeIfNull: false,
  )


  final Map<String, Object>? metadata;



  @JsonKey(
    
    name: r'executed',
    required: false,
    includeIfNull: false,
  )


  final bool? executed;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AgentProposalResponse &&
      other.id == id &&
      other.title == title &&
      other.createdAt == createdAt &&
      other.status == status &&
      other.command == command &&
      other.diff == diff &&
      other.rationale == rationale &&
      other.metadata == metadata &&
      other.executed == executed;

    @override
    int get hashCode =>
        id.hashCode +
        title.hashCode +
        createdAt.hashCode +
        status.hashCode +
        (command == null ? 0 : command.hashCode) +
        (diff == null ? 0 : diff.hashCode) +
        (rationale == null ? 0 : rationale.hashCode) +
        metadata.hashCode +
        executed.hashCode;

  factory AgentProposalResponse.fromJson(Map<String, dynamic> json) => _$AgentProposalResponseFromJson(json);

  Map<String, dynamic> toJson() => _$AgentProposalResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

