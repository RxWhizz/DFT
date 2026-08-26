//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'validation_error.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class ValidationError {
  /// Returns a new [ValidationError] instance.
  ValidationError({

    required  this.loc,

    required  this.msg,

    required  this.type,

     this.input,

     this.ctx,
  });

  @JsonKey(
    
    name: r'loc',
    required: true,
    includeIfNull: false,
  )


  final List<String> loc;



  @JsonKey(
    
    name: r'msg',
    required: true,
    includeIfNull: false,
  )


  final String msg;



  @JsonKey(
    
    name: r'type',
    required: true,
    includeIfNull: false,
  )


  final String type;



  @JsonKey(
    
    name: r'input',
    required: false,
    includeIfNull: false,
  )


  final Object? input;



  @JsonKey(
    
    name: r'ctx',
    required: false,
    includeIfNull: false,
  )


  final Object? ctx;





    @override
    bool operator ==(Object other) => identical(this, other) || other is ValidationError &&
      other.loc == loc &&
      other.msg == msg &&
      other.type == type &&
      other.input == input &&
      other.ctx == ctx;

    @override
    int get hashCode =>
        loc.hashCode +
        msg.hashCode +
        type.hashCode +
        (input == null ? 0 : input.hashCode) +
        ctx.hashCode;

  factory ValidationError.fromJson(Map<String, dynamic> json) => _$ValidationErrorFromJson(json);

  Map<String, dynamic> toJson() => _$ValidationErrorToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

