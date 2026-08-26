String fmtNumber(num? value, [int digits = 2]) {
  if (value == null || value.isNaN) return '-';
  return value.toStringAsFixed(digits);
}

String fmtMinutes(num? value) {
  if (value == null) return '-';
  if (value < 60) return '${value.toStringAsFixed(0)} min';
  return '${(value / 60).toStringAsFixed(1)} h';
}

String fmtFormula(String? value) => value == null || value.isEmpty ? '-' : value;

String wsUrlFromBase(String baseUrl, String path) {
  final uri = Uri.parse(baseUrl);
  final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
  return uri.replace(scheme: scheme, path: path).toString();
}
