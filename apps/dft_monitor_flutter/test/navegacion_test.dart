import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// La barra lateral y el mapeo de rutas tienen que cuadrar.
///
/// Al retirar la pestaña del agente, una expresión regular demasiado avara se
/// llevó por delante también el primer destino. Quedaron 8 destinos para 9
/// índices, así que cada pestaña abría la vista de la siguiente: pulsar
/// «Estructuras» llevaba a lotes, y el visor aparecía bajo «Resultados».
void main() {
  final fuente = File('lib/src/widgets/app_shell.dart').readAsStringSync();

  test('hay un destino por cada indice del mapeo', () {
    final destinos =
        RegExp('NavigationRailDestination\\(').allMatches(fuente).length;

    final indexFor =
        RegExp(r'int _indexFor[\s\S]*?\n\}').firstMatch(fuente)!.group(0)!;
    final indices = RegExp(r'return (\d+);')
        .allMatches(indexFor)
        .map((m) => int.parse(m.group(1)!))
        .toSet();

    final pathFor =
        RegExp(r'String _pathFor[\s\S]*?\n\}').firstMatch(fuente)!.group(0)!;
    final rutas = RegExp(r'(\d+) =>')
        .allMatches(pathFor)
        .map((m) => int.parse(m.group(1)!))
        .toSet();

    expect(
      destinos,
      indices.length,
      reason: '$destinos destinos para ${indices.length} indices en _indexFor',
    );
    expect(
      rutas,
      indices.difference({0}),
      reason: '_pathFor y _indexFor no cubren los mismos indices',
    );
    expect(
      indices,
      equals({for (var i = 0; i < destinos; i++) i}),
      reason: 'los indices deben ser 0..${destinos - 1} sin huecos',
    );
  });

  test('el agente no esta en la barra', () {
    expect(fuente.contains("Text('Agente')"), isFalse);
    expect(fuente.contains("'/agent'"), isFalse);
  });

  test('el protocolo autonomo esta en la barra', () {
    expect(fuente.contains("Text('Protocolo')"), isTrue);
    expect(fuente.contains("'/protocolo-descubrimiento-autonomo'"), isTrue);
  });
}
