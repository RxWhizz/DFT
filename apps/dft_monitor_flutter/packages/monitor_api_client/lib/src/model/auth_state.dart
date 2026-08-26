//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:json_annotation/json_annotation.dart';

part 'auth_state.g.dart';


@JsonSerializable(
  checked: true,
  createToJson: true,
  disallowUnrecognizedKeys: false,
  explicitToJson: true,
)
class AuthState {
  /// Returns a new [AuthState] instance.
  AuthState({

    required  this.authenticated,

    required  this.authEnabled,
  });

  @JsonKey(
    
    name: r'authenticated',
    required: true,
    includeIfNull: false,
  )


  final bool authenticated;



  @JsonKey(
    
    name: r'auth_enabled',
    required: true,
    includeIfNull: false,
  )


  final bool authEnabled;





    @override
    bool operator ==(Object other) => identical(this, other) || other is AuthState &&
      other.authenticated == authenticated &&
      other.authEnabled == authEnabled;

    @override
    int get hashCode =>
        authenticated.hashCode +
        authEnabled.hashCode;

  factory AuthState.fromJson(Map<String, dynamic> json) => _$AuthStateFromJson(json);

  Map<String, dynamic> toJson() => _$AuthStateToJson(this);

  @override
  String toString() {
    return toJson().toString();
  }

}

