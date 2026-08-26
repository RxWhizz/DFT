import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/io.dart';

import '../engine/engine_supervisor.dart';
import '../utils/format.dart';
import 'api_client.dart';

final apiClientProvider = Provider<ApiClient>((ref) {
  final engine = ref.watch(engineSupervisorProvider);
  final ready = engine.ready;
  if (ready == null) throw StateError('Motor local no disponible');
  return ApiClient(ready.baseUrl);
});

final wsEventsProvider = StreamProvider<String>((ref) {
  final api = ref.watch(apiClientProvider);
  final headers = _wsHeaders(api);
  final channel = IOWebSocketChannel.connect(
    Uri.parse(wsUrlFromBase(api.baseUrl, '/ws/events')),
    headers: headers,
  );
  ref.onDispose(channel.sink.close);
  return channel.stream.map((event) => event.toString());
});

final wsEventLogProvider = StreamProvider<List<String>>((ref) async* {
  final api = ref.watch(apiClientProvider);
  final headers = _wsHeaders(api);
  final channel = IOWebSocketChannel.connect(
    Uri.parse(wsUrlFromBase(api.baseUrl, '/ws/events')),
    headers: headers,
  );
  ref.onDispose(channel.sink.close);
  final events = <String>[];
  yield const <String>[];
  await for (final event in channel.stream) {
    final text = event.toString();
    if (text.contains('"type":"event"') || text.contains('"type": "event"')) {
      events.insert(0, text);
      if (events.length > 200) events.removeLast();
      yield List.unmodifiable(events);
    }
  }
});

Map<String, dynamic>? _wsHeaders(ApiClient api) {
  final cookie = api.sessionCookie;
  if (cookie == null || cookie.isEmpty) return null;
  return {'Cookie': cookie};
}
