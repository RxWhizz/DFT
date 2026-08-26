// El analizador marca `use_build_context_synchronously` en cada aviso: no puede
// seguir la comprobación de `mounted` que hace `_avisar`, que es donde vive.
// ignore_for_file: use_build_context_synchronously

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

/// Guardar lo que se ve: la vista 3D como PNG y las tablas como CSV.

/// Rasteriza el widget marcado con [clave] y lo guarda como PNG.
///
/// La captura se hace sobre el `RepaintBoundary`, no sobre la pantalla: sale
/// la figura sola, sin barras ni bordes de la ventana, y a la resolución que se
/// pida en vez de a la del monitor.
Future<String?> guardarPng(
  BuildContext context,
  GlobalKey clave, {
  required String nombre,
  double escala = 3.0,
}) async {
  final objeto = clave.currentContext?.findRenderObject();
  if (objeto is! RenderRepaintBoundary) {
    _avisar(context, 'No hay nada que capturar todavía.');
    return null;
  }

  Uint8List bytes;
  try {
    final imagen = await objeto.toImage(pixelRatio: escala);
    final datos = await imagen.toByteData(format: ui.ImageByteFormat.png);
    imagen.dispose();
    if (datos == null) {
      _avisar(context, 'No se pudo codificar la imagen.');
      return null;
    }
    bytes = datos.buffer.asUint8List();
  } catch (error) {
    _avisar(context, 'No se pudo capturar: $error');
    return null;
  }

  return _escribir(context, bytes, '$nombre.png', 'png', 'Guardar figura');
}

/// Convierte filas a CSV y lo guarda.
///
/// Se usa RFC 4180: comillas dobles alrededor de todo campo con coma, comilla o
/// salto de línea, y las comillas internas duplicadas. Sin eso, una fórmula con
/// coma decimal partiría la fila en dos columnas al abrirla.
Future<String?> guardarCsv(
  BuildContext context, {
  required List<String> cabeceras,
  required List<List<Object?>> filas,
  required String nombre,
}) async {
  final buffer = StringBuffer();
  buffer.writeln(cabeceras.map(_campoCsv).join(','));
  for (final fila in filas) {
    buffer.writeln(fila.map((c) => _campoCsv(c?.toString() ?? '')).join(','));
  }
  // BOM para que Excel abra los acentos y los subíndices sin romperlos, y
  // codificación explícita: `codeUnits` partiría cualquier carácter fuera de
  // Latin-1, que es justo lo que llevan las fórmulas con subíndices.
  final texto = '\u{FEFF}${buffer.toString()}';
  return _escribir(context, Uint8List.fromList(utf8.encode(texto)),
      '$nombre.csv', 'csv', 'Guardar tabla');
}

String _campoCsv(String valor) {
  if (valor.contains(RegExp(r'[",\n\r]'))) {
    return '"${valor.replaceAll('"', '""')}"';
  }
  return valor;
}

Future<String?> _escribir(BuildContext context, Uint8List bytes,
    String sugerido, String extension, String titulo) async {
  String? destino;
  try {
    destino = await FilePicker.platform.saveFile(
      dialogTitle: titulo,
      fileName: sugerido,
      type: FileType.custom,
      allowedExtensions: [extension],
    );
  } catch (error) {
    _avisar(context, 'No se pudo abrir el diálogo: $error');
    return null;
  }
  if (destino == null) return null;      // el usuario canceló

  // El diálogo no siempre añade la extensión.
  if (!destino.toLowerCase().endsWith('.$extension')) {
    destino = '$destino.$extension';
  }

  try {
    await File(destino).writeAsBytes(bytes, flush: true);
  } catch (error) {
    _avisar(context, 'No se pudo escribir: $error');
    return null;
  }
  _avisar(context, 'Guardado en $destino');
  return destino;
}

void _avisar(BuildContext context, String mensaje) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(mensaje)));
}
