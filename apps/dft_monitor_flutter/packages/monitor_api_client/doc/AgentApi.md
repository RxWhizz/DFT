# monitor_api_client.api.AgentApi

## Load the API package
```dart
import 'package:monitor_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**agentChatApiAgentChatPost**](AgentApi.md#agentchatapiagentchatpost) | **POST** /api/agent/chat | Agent Chat
[**agentHealthApiAgentHealthGet**](AgentApi.md#agenthealthapiagenthealthget) | **GET** /api/agent/health | Agent Health
[**approveProposalApiAgentProposalsProposalIdApprovePost**](AgentApi.md#approveproposalapiagentproposalsproposalidapprovepost) | **POST** /api/agent/proposals/{proposal_id}/approve | Approve Proposal
[**rejectProposalApiAgentProposalsProposalIdRejectPost**](AgentApi.md#rejectproposalapiagentproposalsproposalidrejectpost) | **POST** /api/agent/proposals/{proposal_id}/reject | Reject Proposal


# **agentChatApiAgentChatPost**
> AgentChatResponse agentChatApiAgentChatPost(agentChatRequest)

Agent Chat

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAgentApi();
final AgentChatRequest agentChatRequest = ; // AgentChatRequest | 

try {
    final response = api.agentChatApiAgentChatPost(agentChatRequest);
    print(response);
} catch on DioException (e) {
    print('Exception when calling AgentApi->agentChatApiAgentChatPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **agentChatRequest** | [**AgentChatRequest**](AgentChatRequest.md)|  | 

### Return type

[**AgentChatResponse**](AgentChatResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **agentHealthApiAgentHealthGet**
> AgentHealthResponse agentHealthApiAgentHealthGet()

Agent Health

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAgentApi();

try {
    final response = api.agentHealthApiAgentHealthGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling AgentApi->agentHealthApiAgentHealthGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**AgentHealthResponse**](AgentHealthResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **approveProposalApiAgentProposalsProposalIdApprovePost**
> AgentProposalResponse approveProposalApiAgentProposalsProposalIdApprovePost(proposalId)

Approve Proposal

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAgentApi();
final String proposalId = proposalId_example; // String | 

try {
    final response = api.approveProposalApiAgentProposalsProposalIdApprovePost(proposalId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling AgentApi->approveProposalApiAgentProposalsProposalIdApprovePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **proposalId** | **String**|  | 

### Return type

[**AgentProposalResponse**](AgentProposalResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **rejectProposalApiAgentProposalsProposalIdRejectPost**
> AgentProposalResponse rejectProposalApiAgentProposalsProposalIdRejectPost(proposalId)

Reject Proposal

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getAgentApi();
final String proposalId = proposalId_example; // String | 

try {
    final response = api.rejectProposalApiAgentProposalsProposalIdRejectPost(proposalId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling AgentApi->rejectProposalApiAgentProposalsProposalIdRejectPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **proposalId** | **String**|  | 

### Return type

[**AgentProposalResponse**](AgentProposalResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

