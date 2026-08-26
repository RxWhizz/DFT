import 'package:dio/dio.dart';

class ApiClient {
  ApiClient(String baseUrl)
      : dio = Dio(
          BaseOptions(
            baseUrl: baseUrl,
            connectTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 60),
            sendTimeout: const Duration(seconds: 30),
            headers: {'Content-Type': 'application/json'},
          ),
        ),
        baseUrl = baseUrl;

  final String baseUrl;
  final Dio dio;
  String? _sessionCookie;

  String? get sessionCookie => _sessionCookie;

  Options? _options() {
    final cookie = _sessionCookie;
    if (cookie == null || cookie.isEmpty) return null;
    return Options(headers: {'Cookie': cookie});
  }

  void _captureSessionCookie(Headers headers) {
    final values = headers.map['set-cookie'] ?? const <String>[];
    for (final value in values) {
      final cookie = value.split(';').first.trim();
      if (cookie.startsWith('dft_monitor_session=')) {
        _sessionCookie = cookie;
      }
    }
  }

  Future<Map<String, dynamic>> getMap(String path,
      {Map<String, dynamic>? query}) async {
    final response = await dio.get<Object?>(path,
        queryParameters: query, options: _options());
    _captureSessionCookie(response.headers);
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> postMap(
    String path, {
    Object? body,
    Map<String, dynamic>? query,
  }) async {
    final response = await dio.post<Object?>(
      path,
      data: body,
      queryParameters: query,
      options: _options(),
    );
    _captureSessionCookie(response.headers);
    return _asMap(response.data);
  }

  void clearSession() {
    _sessionCookie = null;
  }

  String url(String path, {Map<String, dynamic>? query}) {
    final base = Uri.parse(baseUrl);
    return base
        .replace(
            path: path,
            queryParameters:
                query?.map((key, value) => MapEntry(key, '$value')))
        .toString();
  }
}

Map<String, dynamic> _asMap(Object? data) {
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  throw StateError('Respuesta API inesperada: ${data.runtimeType}');
}
