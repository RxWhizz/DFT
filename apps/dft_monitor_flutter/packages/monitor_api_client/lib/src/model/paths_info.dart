//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'paths_info.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class PathsInfo {
  /// Returns a new [PathsInfo] instance.
  PathsInfo({

    required  this.frozen,

    required  this.bundleRoot,

    required  this.dataRoot,

    required  this.configDir,
  });

  @JsonKey(
    
    name: r'frozen',
    required: true,
    includeIfNull: false,
  )


  final bool frozen;



  @JsonKey(
    
    name: r'bundle_root',
    required: true,
    includeIfNull: false,
  )


  final String bundleRoot;



  @JsonKey(
    
    name: r'data_root',
    required: true,
    includeIfNull: false,
  )


  final String dataRoot;



  @JsonKey(
    
    name: r'config_dir',
    required: true,
    includeIfNull: false,
  )


  final String configDir;





    @override
    bool operator ==(Object other) => identical(this, other) || other is PathsInfo &&
      other.frozen == frozen &&
      other.bundleRoot == bundleRoot &&
      other.dataRoot == dataRoot &&
      other.configDir == configDir;

    @override
    int get hashCode =>
        frozen.hashCode +
        bundleRoot.hashCode +
        dataRoot.hashCode +
        configDir.hashCode;

  factory PathsInfo.fromJson(Map<String, dynamic> json) => _$PathsInfoFromJson(json);

  Map<String, dynamic> toJson() => _$PathsInfoToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

