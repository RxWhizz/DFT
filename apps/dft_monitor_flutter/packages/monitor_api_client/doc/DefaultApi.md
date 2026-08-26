# monitor_api_client.api.DefaultApi

## Load the API package
```dart
import 'package:monitor_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getJobApiJobsJobIdGet**](DefaultApi.md#getjobapijobsjobidget) | **GET** /api/jobs/{job_id} | Get Job
[**getStatsApiJobsJobIdStatsGet**](DefaultApi.md#getstatsapijobsjobidstatsget) | **GET** /api/jobs/{job_id}/stats | Get Stats
[**healthApiHealthGet**](DefaultApi.md#healthapihealthget) | **GET** /api/health | Health
[**jobLogApiJobsJobIdLogGet**](DefaultApi.md#joblogapijobsjobidlogget) | **GET** /api/jobs/{job_id}/log | Job Log
[**jobMetadataEndpointApiJobsJobIdMetadataGet**](DefaultApi.md#jobmetadataendpointapijobsjobidmetadataget) | **GET** /api/jobs/{job_id}/metadata | Job Metadata Endpoint
[**jobTracesEndpointApiJobsJobIdTracesGet**](DefaultApi.md#jobtracesendpointapijobsjobidtracesget) | **GET** /api/jobs/{job_id}/traces | Job Traces Endpoint
[**killJobEndpointApiJobsJobIdKillPost**](DefaultApi.md#killjobendpointapijobsjobidkillpost) | **POST** /api/jobs/{job_id}/kill | Kill Job Endpoint
[**listBatchesEndpointApiBatchesGet**](DefaultApi.md#listbatchesendpointapibatchesget) | **GET** /api/batches | List Batches Endpoint
[**listCandidatesApiCandidatesGet**](DefaultApi.md#listcandidatesapicandidatesget) | **GET** /api/candidates | List Candidates
[**listConvergedApiJobsConvergedGet**](DefaultApi.md#listconvergedapijobsconvergedget) | **GET** /api/jobs/converged | List Converged
[**listJobsApiJobsGet**](DefaultApi.md#listjobsapijobsget) | **GET** /api/jobs | List Jobs
[**listModelsApiModelsGet**](DefaultApi.md#listmodelsapimodelsget) | **GET** /api/models | List Models
[**listReportsEndpointApiReportsGet**](DefaultApi.md#listreportsendpointapireportsget) | **GET** /api/reports | List Reports Endpoint
[**listStructuresEndpointApiStructuresGet**](DefaultApi.md#liststructuresendpointapistructuresget) | **GET** /api/structures | List Structures Endpoint
[**mlPredictApiMlPredictPost**](DefaultApi.md#mlpredictapimlpredictpost) | **POST** /api/ml/predict | Ml Predict
[**mlTop8ApiMlTop8Get**](DefaultApi.md#mltop8apimltop8get) | **GET** /api/ml/top8 | Ml Top8
[**notifyConvergedApiNotifyConvergedPost**](DefaultApi.md#notifyconvergedapinotifyconvergedpost) | **POST** /api/notify/converged | Notify Converged
[**notifyStatusApiNotifyStatusPost**](DefaultApi.md#notifystatusapinotifystatuspost) | **POST** /api/notify/status | Notify Status
[**notifyTestApiNotifyTestPost**](DefaultApi.md#notifytestapinotifytestpost) | **POST** /api/notify/test | Notify Test
[**pingApiJobsJobIdPingGet**](DefaultApi.md#pingapijobsjobidpingget) | **GET** /api/jobs/{job_id}/ping | Ping
[**reportDocumentApiReportsDocumentGet**](DefaultApi.md#reportdocumentapireportsdocumentget) | **GET** /api/reports/document | Report Document
[**reportFigureApiReportsFigureGet**](DefaultApi.md#reportfigureapireportsfigureget) | **GET** /api/reports/figure | Report Figure
[**retryJobEndpointApiJobsJobIdRetryPost**](DefaultApi.md#retryjobendpointapijobsjobidretrypost) | **POST** /api/jobs/{job_id}/retry | Retry Job Endpoint
[**screeningConfigApiScreeningConfigGet**](DefaultApi.md#screeningconfigapiscreeningconfigget) | **GET** /api/screening/config | Screening Config
[**screeningRunApiScreeningRunPost**](DefaultApi.md#screeningrunapiscreeningrunpost) | **POST** /api/screening/run | Screening Run
[**screeningRunDetailApiScreeningRunsRunIdGet**](DefaultApi.md#screeningrundetailapiscreeningrunsrunidget) | **GET** /api/screening/runs/{run_id} | Screening Run Detail
[**screeningRunsApiScreeningRunsGet**](DefaultApi.md#screeningrunsapiscreeningrunsget) | **GET** /api/screening/runs | Screening Runs
[**screeningStartDftApiScreeningRunsRunIdStartDftPost**](DefaultApi.md#screeningstartdftapiscreeningrunsrunidstartdftpost) | **POST** /api/screening/runs/{run_id}/start-dft | Screening Start Dft
[**startBatchEndpointApiBatchesBatchIdStartPost**](DefaultApi.md#startbatchendpointapibatchesbatchidstartpost) | **POST** /api/batches/{batch_id}/start | Start Batch Endpoint
[**statusReportApiStatusReportGet**](DefaultApi.md#statusreportapistatusreportget) | **GET** /api/status/report | Status Report
[**statusfullReportApiStatusfullGet**](DefaultApi.md#statusfullreportapistatusfullget) | **GET** /api/statusfull | Statusfull Report
[**structureContentApiStructuresContentGet**](DefaultApi.md#structurecontentapistructurescontentget) | **GET** /api/structures/content | Structure Content
[**summaryApiSummaryGet**](DefaultApi.md#summaryapisummaryget) | **GET** /api/summary | Summary
[**systemHistoryApiSystemHistoryGet**](DefaultApi.md#systemhistoryapisystemhistoryget) | **GET** /api/system/history | System History
[**systemMetricsApiSystemGet**](DefaultApi.md#systemmetricsapisystemget) | **GET** /api/system | System Metrics


# **getJobApiJobsJobIdGet**
> StatsResponse getJobApiJobsJobIdGet(jobId)

Get Job

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.getJobApiJobsJobIdGet(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->getJobApiJobsJobIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**StatsResponse**](StatsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStatsApiJobsJobIdStatsGet**
> StatsResponse getStatsApiJobsJobIdStatsGet(jobId)

Get Stats

Igual que GET /api/jobs/{job_id} pero fuerza re-parseo del disco.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.getStatsApiJobsJobIdStatsGet(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->getStatsApiJobsJobIdStatsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**StatsResponse**](StatsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **healthApiHealthGet**
> HealthResponse healthApiHealthGet()

Health

Salud del monitor: montaje de `runs_dir`, frescura del poller, clientes WS.  `runs_mounted` existe porque `runs/` y `calculations/` son symlinks a un volumen externo. Sin esta señal, \"el disco está desmontado\" y \"no hay jobs\" se ven exactamente igual desde el cliente.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.healthApiHealthGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->healthApiHealthGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**HealthResponse**](HealthResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **jobLogApiJobsJobIdLogGet**
> Map<String, Object> jobLogApiJobsJobIdLogGet(jobId, label, tail)

Job Log

Cola del log del job. `available` lista las etiquetas seleccionables.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 
final String label = label_example; // String | Sub-cálculo; por defecto el primero disponible.
final int tail = 56; // int | Últimas N líneas.

try {
    final response = api.jobLogApiJobsJobIdLogGet(jobId, label, tail);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->jobLogApiJobsJobIdLogGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 
 **label** | **String**| Sub-cálculo; por defecto el primero disponible. | [optional] 
 **tail** | **int**| Últimas N líneas. | [optional] 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **jobMetadataEndpointApiJobsJobIdMetadataGet**
> Map<String, Object> jobMetadataEndpointApiJobsJobIdMetadataGet(jobId)

Job Metadata Endpoint

metadata.json y status.json del job, más el inventario de artefactos.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.jobMetadataEndpointApiJobsJobIdMetadataGet(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->jobMetadataEndpointApiJobsJobIdMetadataGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **jobTracesEndpointApiJobsJobIdTracesGet**
> Map<String, Object> jobTracesEndpointApiJobsJobIdTracesGet(jobId)

Job Traces Endpoint

Series SCF por etiqueta y resumen de los frames etiquetados con DFT.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.jobTracesEndpointApiJobsJobIdTracesGet(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->jobTracesEndpointApiJobsJobIdTracesGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **killJobEndpointApiJobsJobIdKillPost**
> Map<String, Object> killJobEndpointApiJobsJobIdKillPost(jobId)

Kill Job Endpoint

Detiene los procesos de un job. Acción destructiva: queda auditada.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.killJobEndpointApiJobsJobIdKillPost(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->killJobEndpointApiJobsJobIdKillPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listBatchesEndpointApiBatchesGet**
> Map<String, Object> listBatchesEndpointApiBatchesGet()

List Batches Endpoint

Batches con su recuento por estado, throughput y ETA.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.listBatchesEndpointApiBatchesGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listBatchesEndpointApiBatchesGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listCandidatesApiCandidatesGet**
> Map<String, Object> listCandidatesApiCandidatesGet(q, generationMode, bFamily, halide, sort, desc, limit, offset)

List Candidates

Candidatos del generador BUHO.  `source` indica de dónde salieron: el CSV del generador si está disponible, o los metadata.json de los jobs como alternativa.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String q = q_example; // String | Subcadena en la fórmula.
final String generationMode = generationMode_example; // String | pure/A_mixed/B_mixed/X_mixed, coma.
final String bFamily = bFamily_example; // String | Familia del sitio B, coma.
final String halide = halide_example; // String | Haluro dominante, coma.
final String sort = sort_example; // String | 
final bool desc = true; // bool | 
final int limit = 56; // int | 
final int offset = 56; // int | 

try {
    final response = api.listCandidatesApiCandidatesGet(q, generationMode, bFamily, halide, sort, desc, limit, offset);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listCandidatesApiCandidatesGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **q** | **String**| Subcadena en la fórmula. | [optional] 
 **generationMode** | **String**| pure/A_mixed/B_mixed/X_mixed, coma. | [optional] 
 **bFamily** | **String**| Familia del sitio B, coma. | [optional] 
 **halide** | **String**| Haluro dominante, coma. | [optional] 
 **sort** | **String**|  | [optional] 
 **desc** | **bool**|  | [optional] 
 **limit** | **int**|  | [optional] 
 **offset** | **int**|  | [optional] 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listConvergedApiJobsConvergedGet**
> List<JobStatus> listConvergedApiJobsConvergedGet(limit)

List Converged

Lista los primeros N jobs convergidos ordenados por fórmula.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final int limit = 56; // int | 

try {
    final response = api.listConvergedApiJobsConvergedGet(limit);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listConvergedApiJobsConvergedGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **limit** | **int**|  | [optional] 

### Return type

[**List&lt;JobStatus&gt;**](JobStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listJobsApiJobsGet**
> JobPage listJobsApiJobsGet(status, q, sort, desc, limit, offset)

List Jobs

Jobs paginados, con filtro y orden.  Devolver los ~2500 snapshots enteros en cada carga eran varios MB de JSON.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String status = status_example; // String | Estado a filtrar; admite lista separada por comas.
final String q = q_example; // String | Subcadena buscada en la fórmula o el job_id.
final String sort = sort_example; // String | 
final bool desc = true; // bool | 
final int limit = 56; // int | 
final int offset = 56; // int | 

try {
    final response = api.listJobsApiJobsGet(status, q, sort, desc, limit, offset);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listJobsApiJobsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **status** | **String**| Estado a filtrar; admite lista separada por comas. | [optional] 
 **q** | **String**| Subcadena buscada en la fórmula o el job_id. | [optional] 
 **sort** | **String**|  | [optional] 
 **desc** | **bool**|  | [optional] 
 **limit** | **int**|  | [optional] 
 **offset** | **int**|  | [optional] 

### Return type

[**JobPage**](JobPage.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listModelsApiModelsGet**
> Map<String, Object> listModelsApiModelsGet()

List Models

Métricas de los surrogates y estado de carga del modelo de bandgap.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.listModelsApiModelsGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listModelsApiModelsGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listReportsEndpointApiReportsGet**
> Map<String, Object> listReportsEndpointApiReportsGet()

List Reports Endpoint

Reportes Markdown y galerías declaradas en los visualization_manifest.json.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.listReportsEndpointApiReportsGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listReportsEndpointApiReportsGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listStructuresEndpointApiStructuresGet**
> Map<String, Object> listStructuresEndpointApiStructuresGet()

List Structures Endpoint

Estructuras disponibles: fases de referencia, top-8 y las de cada job.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.listStructuresEndpointApiStructuresGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->listStructuresEndpointApiStructuresGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **mlPredictApiMlPredictPost**
> Map<String, Object> mlPredictApiMlPredictPost(predictRequest)

Ml Predict

Bandgap predicho con incertidumbre bootstrap para una composición ABX3.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final PredictRequest predictRequest = ; // PredictRequest | 

try {
    final response = api.mlPredictApiMlPredictPost(predictRequest);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->mlPredictApiMlPredictPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **predictRequest** | [**PredictRequest**](PredictRequest.md)|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **mlTop8ApiMlTop8Get**
> Map<String, Object> mlTop8ApiMlTop8Get()

Ml Top8

Predicción ML frente a DFT y experimento para los 8 candidatos top.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.mlTop8ApiMlTop8Get();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->mlTop8ApiMlTop8Get: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **notifyConvergedApiNotifyConvergedPost**
> Map<String, Object> notifyConvergedApiNotifyConvergedPost(limit)

Notify Converged

Envía a Telegram los primeros N convergidos que quepan en 4096 chars.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final int limit = 56; // int | 

try {
    final response = api.notifyConvergedApiNotifyConvergedPost(limit);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->notifyConvergedApiNotifyConvergedPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **limit** | **int**|  | [optional] 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **notifyStatusApiNotifyStatusPost**
> Map<String, Object> notifyStatusApiNotifyStatusPost()

Notify Status

Envía reporte STATUS completo a Telegram ahora.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.notifyStatusApiNotifyStatusPost();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->notifyStatusApiNotifyStatusPost: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **notifyTestApiNotifyTestPost**
> Map<String, Object> notifyTestApiNotifyTestPost()

Notify Test

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.notifyTestApiNotifyTestPost();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->notifyTestApiNotifyTestPost: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **pingApiJobsJobIdPingGet**
> PingResponse pingApiJobsJobIdPingGet(jobId)

Ping

Lectura instantánea del log actual — no usa caché.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.pingApiJobsJobIdPingGet(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->pingApiJobsJobIdPingGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**PingResponse**](PingResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **reportDocumentApiReportsDocumentGet**
> Map<String, Object> reportDocumentApiReportsDocumentGet(path)

Report Document

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String path = path_example; // String | Ruta relativa al repo, dentro de reports/ o imagenes/.

try {
    final response = api.reportDocumentApiReportsDocumentGet(path);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->reportDocumentApiReportsDocumentGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **path** | **String**| Ruta relativa al repo, dentro de reports/ o imagenes/. | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **reportFigureApiReportsFigureGet**
> Object reportFigureApiReportsFigureGet(path)

Report Figure

Sirve una figura. Muchas están en .gitignore y pueden no existir.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String path = path_example; // String | Ruta relativa al repo de una figura.

try {
    final response = api.reportFigureApiReportsFigureGet(path);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->reportFigureApiReportsFigureGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **path** | **String**| Ruta relativa al repo de una figura. | 

### Return type

**Object**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **retryJobEndpointApiJobsJobIdRetryPost**
> Map<String, Object> retryJobEndpointApiJobsJobIdRetryPost(jobId)

Retry Job Endpoint

Devuelve un job fallido a la cola para que el runner lo recoja.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.retryJobEndpointApiJobsJobIdRetryPost(jobId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->retryJobEndpointApiJobsJobIdRetryPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **screeningConfigApiScreeningConfigGet**
> Map<String, Object> screeningConfigApiScreeningConfigGet()

Screening Config

Cotas de la cascada y disponibilidad real de cada tier.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.screeningConfigApiScreeningConfigGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->screeningConfigApiScreeningConfigGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **screeningRunApiScreeningRunPost**
> Map<String, Object> screeningRunApiScreeningRunPost(screeningRunRequest)

Screening Run

Arranca la cascada en segundo plano y devuelve el identificador.  Tarda minutos: se consulta el progreso en /api/screening/runs/{run_id}.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final ScreeningRunRequest screeningRunRequest = ; // ScreeningRunRequest | 

try {
    final response = api.screeningRunApiScreeningRunPost(screeningRunRequest);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->screeningRunApiScreeningRunPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **screeningRunRequest** | [**ScreeningRunRequest**](ScreeningRunRequest.md)|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **screeningRunDetailApiScreeningRunsRunIdGet**
> Map<String, Object> screeningRunDetailApiScreeningRunsRunIdGet(runId, limit)

Screening Run Detail

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String runId = runId_example; // String | 
final int limit = 56; // int | Filas del ranking a devolver.

try {
    final response = api.screeningRunDetailApiScreeningRunsRunIdGet(runId, limit);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->screeningRunDetailApiScreeningRunsRunIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **runId** | **String**|  | 
 **limit** | **int**| Filas del ranking a devolver. | [optional] 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **screeningRunsApiScreeningRunsGet**
> Map<String, Object> screeningRunsApiScreeningRunsGet()

Screening Runs

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.screeningRunsApiScreeningRunsGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->screeningRunsApiScreeningRunsGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **screeningStartDftApiScreeningRunsRunIdStartDftPost**
> Map<String, Object> screeningStartDftApiScreeningRunsRunIdStartDftPost(runId, screeningStartDftRequest)

Screening Start Dft

Prepara los seleccionados del cribado como jobs DFT y puede lanzar el runner.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String runId = runId_example; // String | 
final ScreeningStartDftRequest screeningStartDftRequest = ; // ScreeningStartDftRequest | 

try {
    final response = api.screeningStartDftApiScreeningRunsRunIdStartDftPost(runId, screeningStartDftRequest);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->screeningStartDftApiScreeningRunsRunIdStartDftPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **runId** | **String**|  | 
 **screeningStartDftRequest** | [**ScreeningStartDftRequest**](ScreeningStartDftRequest.md)|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **startBatchEndpointApiBatchesBatchIdStartPost**
> Map<String, Object> startBatchEndpointApiBatchesBatchIdStartPost(batchId)

Start Batch Endpoint

Lanza el runner de un batch. Arranca un proceso: queda auditado.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final int batchId = 56; // int | 

try {
    final response = api.startBatchEndpointApiBatchesBatchIdStartPost(batchId);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->startBatchEndpointApiBatchesBatchIdStartPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **batchId** | **int**|  | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **statusReportApiStatusReportGet**
> Map<String, Object> statusReportApiStatusReportGet()

Status Report

Devuelve el reporte STATUS completo como texto.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.statusReportApiStatusReportGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->statusReportApiStatusReportGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **statusfullReportApiStatusfullGet**
> Map<String, Object> statusfullReportApiStatusfullGet()

Statusfull Report

Devuelve el reporte statusfull (detalle SCF por job activo) como lista de mensajes.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.statusfullReportApiStatusfullGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->statusfullReportApiStatusfullGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **structureContentApiStructuresContentGet**
> Map<String, Object> structureContentApiStructuresContentGet(id)

Structure Content

Estructura en CIF. Los structures/_*.json de ASE se convierten al vuelo.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final String id = id_example; // String | Identificador de /api/structures (repo:… o job:…).

try {
    final response = api.structureContentApiStructuresContentGet(id);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->structureContentApiStructuresContentGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **String**| Identificador de /api/structures (repo:… o job:…). | 

### Return type

**Map&lt;String, Object&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **summaryApiSummaryGet**
> SummaryResponse summaryApiSummaryGet()

Summary

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.summaryApiSummaryGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->summaryApiSummaryGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SummaryResponse**](SummaryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **systemHistoryApiSystemHistoryGet**
> MetricsHistoryResponse systemHistoryApiSystemHistoryGet(minutes)

System History

Serie reciente de CPU, RAM y temperatura, para las sparklines.  `/api/system` solo da el instante actual.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();
final int minutes = 56; // int | Ventana en minutos.

try {
    final response = api.systemHistoryApiSystemHistoryGet(minutes);
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->systemHistoryApiSystemHistoryGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **minutes** | **int**| Ventana en minutos. | [optional] 

### Return type

[**MetricsHistoryResponse**](MetricsHistoryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **systemMetricsApiSystemGet**
> SysMetricsResponse systemMetricsApiSystemGet()

System Metrics

Temperaturas, uso de CPU y RAM en tiempo real.

### Example
```dart
import 'package:monitor_api_client/api.dart';

final api = MonitorApiClient().getDefaultApi();

try {
    final response = api.systemMetricsApiSystemGet();
    print(response);
} catch on DioException (e) {
    print('Exception when calling DefaultApi->systemMetricsApiSystemGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SysMetricsResponse**](SysMetricsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

