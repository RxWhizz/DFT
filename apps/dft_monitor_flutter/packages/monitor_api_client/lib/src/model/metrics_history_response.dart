//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'metrics_history_response.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class MetricsHistoryResponse {
  /// Returns a new [MetricsHistoryResponse] instance.
  MetricsHistoryResponse({

    required  this.samples,

    required  this.intervalSec,
  });

  @JsonKey(
    
    name: r'samples',
    required: true,
    includeIfNull: false,
  )


  final List<Map<String, Object>> samples;



  @JsonKey(
    
    name: r'interval_sec',
    required: true,
    includeIfNull: false,
  )


  final int intervalSec;





    @override
    bool operator ==(Object other) => identical(this, other) || other is MetricsHistoryResponse &&
      other.samples == samples &&
      other.intervalSec == intervalSec;

    @override
    int get hashCode =>
        samples.hashCode +
        intervalSec.hashCode;

  factory MetricsHistoryResponse.fromJson(Map<String, dynamic> json) => _$MetricsHistoryResponseFromJson(json);

  Map<String, dynamic> toJson() => _$MetricsHistoryResponseToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

