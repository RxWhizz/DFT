//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'screening_start_dft_request.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class ScreeningStartDftRequest {
  /// Returns a new [ScreeningStartDftRequest] instance.
  ScreeningStartDftRequest({

     this.startRunner,
  });

  @JsonKey(
    
    name: r'start_runner',
    required: false,
    includeIfNull: false,
  )


  final bool? startRunner;





    @override
    bool operator ==(Object other) => identical(this, other) || other is ScreeningStartDftRequest &&
      other.startRunner == startRunner;

    @override
    int get hashCode =>
        startRunner.hashCode;

  factory ScreeningStartDftRequest.fromJson(Map<String, dynamic> json) => _$ScreeningStartDftRequestFromJson(json);

  Map<String, dynamic> toJson() => _$ScreeningStartDftRequestToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

