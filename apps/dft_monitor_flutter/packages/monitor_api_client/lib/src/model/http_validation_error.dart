//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:monitor_api_client/src/model/validation_error.dart';
import 'package:json_annotation/json_annotation.dart';

part 'http_validation_error.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class HTTPValidationError {
  /// Returns a new [HTTPValidationError] instance.
  HTTPValidationError({

     this.detail,
  });

  @JsonKey(
    
    name: r'detail',
    required: false,
    includeIfNull: false,
  )


  final List<ValidationError>? detail;





    @override
    bool operator ==(Object other) => identical(this, other) || other is HTTPValidationError &&
      other.detail == detail;

    @override
    int get hashCode =>
        detail.hashCode;

  factory HTTPValidationError.fromJson(Map<String, dynamic> json) => _$HTTPValidationErrorFromJson(json);

  Map<String, dynamic> toJson() => _$HTTPValidationErrorToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

