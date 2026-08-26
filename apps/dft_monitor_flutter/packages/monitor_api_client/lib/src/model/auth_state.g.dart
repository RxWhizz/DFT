// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'auth_state.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

AuthState _$AuthStateFromJson(Map<String, dynamic> json) =>
    $checkedCreate('AuthState', json, ($checkedConvert) {
      $checkKeys(json, requiredKeys: const ['authenticated', 'auth_enabled']);
      final val = AuthState(
        authenticated: $checkedConvert('authenticated', (v) => v as bool),
        authEnabled: $checkedConvert('auth_enabled', (v) => v as bool),
      );
      return val;
    }, fieldKeyMap: const {'authEnabled': 'auth_enabled'});

Map<String, dynamic> _$AuthStateToJson(AuthState instance) => <String, dynamic>{
  'authenticated': instance.authenticated,
  'auth_enabled': instance.authEnabled,
};
