import 'package:dio/dio.dart';

/// Traduce un error de la API a algo que se pueda leer.
///
/// FastAPI manda el motivo en `detail`, pero `DioException.toString()` lo
/// descarta y deja «The request returned an invalid status code of 409», que no
/// le dice nada a nadie: el backend sí explicaba que ya había un runner activo
/// para ese batch.
String mensajeDeError(Object error) {
  if (error is! DioException) return '$error';

  final data = error.response?.data;
  if (data is Map) {
    final detail = data['detail'];
    if (detail is String && detail.isNotEmpty) return detail;
    // Errores de validación de Pydantic: lista de {loc, msg, type}.
    if (detail is List && detail.isNotEmpty) {
      return detail
          .map((e) => e is Map ? '${e['msg'] ?? e}' : '$e')
          .join('; ');
    }
    if (detail != null) return '$detail';
  }

  switch (error.type) {
    case DioExceptionType.connectionError:
    case DioExceptionType.connectionTimeout:
      return 'Sin conexion con el motor.';
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.sendTimeout:
      return 'El motor tardo demasiado en responder.';
    default:
      break;
  }

  final code = error.response?.statusCode;
  return code == null ? '$error' : 'El motor respondio $code.';
}
