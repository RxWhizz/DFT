import 'package:monitor_api_client/src/model/agent_chat_request.dart';
import 'package:monitor_api_client/src/model/agent_chat_response.dart';
import 'package:monitor_api_client/src/model/agent_health_response.dart';
import 'package:monitor_api_client/src/model/agent_message.dart';
import 'package:monitor_api_client/src/model/agent_proposal_response.dart';
import 'package:monitor_api_client/src/model/agent_tool_result.dart';
import 'package:monitor_api_client/src/model/auth_state.dart';
import 'package:monitor_api_client/src/model/http_validation_error.dart';
import 'package:monitor_api_client/src/model/health_response.dart';
import 'package:monitor_api_client/src/model/job_page.dart';
import 'package:monitor_api_client/src/model/job_status.dart';
import 'package:monitor_api_client/src/model/login_request.dart';
import 'package:monitor_api_client/src/model/metrics_history_response.dart';
import 'package:monitor_api_client/src/model/paths_info.dart';
import 'package:monitor_api_client/src/model/ping_response.dart';
import 'package:monitor_api_client/src/model/platform_info.dart';
import 'package:monitor_api_client/src/model/predict_request.dart';
import 'package:monitor_api_client/src/model/screening_run_request.dart';
import 'package:monitor_api_client/src/model/screening_start_dft_request.dart';
import 'package:monitor_api_client/src/model/stats_response.dart';
import 'package:monitor_api_client/src/model/summary_response.dart';
import 'package:monitor_api_client/src/model/sys_metrics_response.dart';
import 'package:monitor_api_client/src/model/validation_error.dart';

final _regList = RegExp(r'^List<(.*)>$');
final _regSet = RegExp(r'^Set<(.*)>$');
final _regMap = RegExp(r'^Map<String,(.*)>$');

  ReturnType deserialize<ReturnType, BaseType>(dynamic value, String targetType, {bool growable= true}) {
      switch (targetType) {
        case 'String':
          return '$value' as ReturnType;
        case 'int':
          return (value is int ? value : int.parse('$value')) as ReturnType;
        case 'bool':
          if (value is bool) {
            return value as ReturnType;
          }
          final valueString = '$value'.toLowerCase();
          return (valueString == 'true' || valueString == '1') as ReturnType;
        case 'double':
          return (value is double ? value : double.parse('$value')) as ReturnType;
        case 'AgentChatRequest':
          return AgentChatRequest.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'AgentChatResponse':
          return AgentChatResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'AgentHealthResponse':
          return AgentHealthResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'AgentMessage':
          return AgentMessage.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'AgentProposalResponse':
          return AgentProposalResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'AgentToolResult':
          return AgentToolResult.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'AuthState':
          return AuthState.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'HTTPValidationError':
          return HTTPValidationError.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'HealthResponse':
          return HealthResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'JobPage':
          return JobPage.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'JobStatus':
          return JobStatus.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'LoginRequest':
          return LoginRequest.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'MetricsHistoryResponse':
          return MetricsHistoryResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'PathsInfo':
          return PathsInfo.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'PingResponse':
          return PingResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'PlatformInfo':
          return PlatformInfo.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'PredictRequest':
          return PredictRequest.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'ScreeningRunRequest':
          return ScreeningRunRequest.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'ScreeningStartDftRequest':
          return ScreeningStartDftRequest.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'StatsResponse':
          return StatsResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'SummaryResponse':
          return SummaryResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'SysMetricsResponse':
          return SysMetricsResponse.fromJson(value as Map<String, dynamic>) as ReturnType;
        case 'ValidationError':
          return ValidationError.fromJson(value as Map<String, dynamic>) as ReturnType;
        default:
          RegExpMatch? match;

          if (value is List && (match = _regList.firstMatch(targetType)) != null) {
            targetType = match![1]!; // ignore: parameter_assignments
            return value
              .map<BaseType>((dynamic v) => deserialize<BaseType, BaseType>(v, targetType, growable: growable))
              .toList(growable: growable) as ReturnType;
          }
          if (value is Set && (match = _regSet.firstMatch(targetType)) != null) {
            targetType = match![1]!; // ignore: parameter_assignments
            return value
              .map<BaseType>((dynamic v) => deserialize<BaseType, BaseType>(v, targetType, growable: growable))
              .toSet() as ReturnType;
          }
          if (value is Map && (match = _regMap.firstMatch(targetType)) != null) {
            targetType = match![1]!.trim(); // ignore: parameter_assignments
            return Map<String, BaseType>.fromIterables(
              value.keys as Iterable<String>,
              value.values.map((dynamic v) => deserialize<BaseType, BaseType>(v, targetType, growable: growable)),
            ) as ReturnType;
          }
          break;
    }
    throw Exception('Cannot deserialize');
  }