//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'platform_info.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class PlatformInfo {
  /// Returns a new [PlatformInfo] instance.
  PlatformInfo({

    required  this.os,

    required  this.frozen,

    required  this.hardwareTemps,

    required  this.runnerLaunch,

     this.runnerPython,

     this.autoAdvance,
  });

  @JsonKey(
    
    name: r'os',
    required: true,
    includeIfNull: false,
  )


  final String os;



  @JsonKey(
    
    name: r'frozen',
    required: true,
    includeIfNull: false,
  )


  final bool frozen;



  @JsonKey(
    
    name: r'hardware_temps',
    required: true,
    includeIfNull: false,
  )


  final bool hardwareTemps;



  @JsonKey(
    
    name: r'runner_launch',
    required: true,
    includeIfNull: false,
  )


  final bool runnerLaunch;



  @JsonKey(
    
    name: r'runner_python',
    required: false,
    includeIfNull: false,
  )


  final String? runnerPython;



  @JsonKey(
    
    name: r'auto_advance',
    required: false,
    includeIfNull: false,
  )


  final bool? autoAdvance;





    @override
    bool operator ==(Object other) => identical(this, other) || other is PlatformInfo &&
      other.os == os &&
      other.frozen == frozen &&
      other.hardwareTemps == hardwareTemps &&
      other.runnerLaunch == runnerLaunch &&
      other.runnerPython == runnerPython &&
      other.autoAdvance == autoAdvance;

    @override
    int get hashCode =>
        os.hashCode +
        frozen.hashCode +
        hardwareTemps.hashCode +
        runnerLaunch.hashCode +
        (runnerPython == null ? 0 : runnerPython.hashCode) +
        autoAdvance.hashCode;

  factory PlatformInfo.fromJson(Map<String, dynamic> json) => _$PlatformInfoFromJson(json);

  Map<String, dynamic> toJson() => _$PlatformInfoToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

