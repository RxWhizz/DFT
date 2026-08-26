# monitor_api_client.api.AuthApi

## Load the API package
```dart
import 'package:monitor_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**loginAuthLoginPost**](AuthApi.md#loginauthloginpost) | **POST** /auth/login | Login
[**logoutAuthLogoutPost**](AuthApi.md#logoutauthlogoutpost) | **POST** /auth/logout | Logout
[**meAuthMeGet**](AuthApi.md#meauthmeget) | **GET** /auth/me | Me


# **loginAuthLoginPost**
> AuthState loginAuthLoginPost(loginRequest)

Login

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAuthApi();
final LoginRequest loginRequest = ; // LoginRequest | 

try {
    final response = api.loginAuthLoginPost(loginRequest);
    print(response);
} catch on DioException (e) {
    print('Exception when calling AuthApi->loginAuthLoginPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **loginRequest** | [**LoginRequest**](LoginRequest.md)|  | 

### Return type

[**AuthState**](AuthState.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **logoutAuthLogoutPost**
> AuthState logoutAuthLogoutPost()

Logout

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAuthApi();

try {
    final response = api.logoutAuthLogoutPost();
    print(response);
} catch on DioException (e) {
    print('Exception when calling AuthApi->logoutAuthLogoutPost: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**AuthState**](AuthState.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **meAuthMeGet**
> AuthState meAuthMeGet()

Me

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAuthApi();

try {
    final response = api.meAuthMeGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling AuthApi->meAuthMeGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**AuthState**](AuthState.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

