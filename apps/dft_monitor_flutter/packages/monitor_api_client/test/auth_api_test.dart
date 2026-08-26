import 'package:test/test.dart';
import 'package:monitor_api_client/monitor_api_client.dart';


/// tests for AuthApi
void main() {
  final instance = MonitorApiClient().getAuthApi();

  group(AuthApi, () {
    // Login
    //
    //Future<AuthState> loginAuthLoginPost(LoginRequest loginRequest) async
    test('test loginAuthLoginPost', () async {
      // TODO
    });

    // Logout
    //
    //Future<AuthState> logoutAuthLogoutPost() async
    test('test logoutAuthLogoutPost', () async {
      // TODO
    });

    // Me
    //
    //Future<AuthState> meAuthMeGet() async
    test('test meAuthMeGet', () async {
      // TODO
    });

  });
}
