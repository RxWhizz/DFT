//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:monitor_api_client/src/model/job_status.dart';
import 'package:json_annotation/json_annotation.dart';

part 'job_page.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class JobPage {
  /// Returns a new [JobPage] instance.
  JobPage({

    required  this.items,

    required  this.total,

    required  this.limit,

    required  this.offset,
  });

  @JsonKey(
    
    name: r'items',
    required: true,
    includeIfNull: false,
  )


  final List<JobStatus> items;



  @JsonKey(
    
    name: r'total',
    required: true,
    includeIfNull: false,
  )


  final int total;



  @JsonKey(
    
    name: r'limit',
    required: true,
    includeIfNull: false,
  )


  final int limit;



  @JsonKey(
    
    name: r'offset',
    required: true,
    includeIfNull: false,
  )


  final int offset;





    @override
    bool operator ==(Object other) => identical(this, other) || other is JobPage &&
      other.items == items &&
      other.total == total &&
      other.limit == limit &&
      other.offset == offset;

    @override
    int get hashCode =>
        items.hashCode +
        total.hashCode +
        limit.hashCode +
        offset.hashCode;

  factory JobPage.fromJson(Map<String, dynamic> json) => _$JobPageFromJson(json);

  Map<String, dynamic> toJson() => _$JobPageToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

