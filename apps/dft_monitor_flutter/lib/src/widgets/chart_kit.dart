import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Piezas comunes de las gráficas: paleta, ejes con nombre y marcas, leyenda.
///
/// Las dos gráficas dibujaban con hexadecimales fijos pensados para fondo
/// oscuro —invisibles en tema claro—, sin nombres de ejes ni valores en las
/// marcas: se veía una nube de puntos sin saber de qué.

/// Paleta categórica validada para daltonismo sobre ambos fondos.
///
/// Comprobada con el validador de la guía de visualización: peor par
/// ΔE 26.8 (oscuro) y 24.7 (claro) en protanopia, contra un umbral de 8.
class VizPalette {
  const VizPalette._(this.oscuro);

  factory VizPalette.of(BuildContext context) =>
      VizPalette._(Theme.of(context).brightness == Brightness.dark);

  final bool oscuro;

  /// Serie 1 — azul.
  Color get serie1 => oscuro ? const Color(0xff3987e5) : const Color(0xff2a78d6);

  /// Serie 2 — naranja.
  Color get serie2 => oscuro ? const Color(0xffd95926) : const Color(0xffeb6834);

  /// Región válida / estado correcto. Nunca va sola: siempre lleva etiqueta.
  Color get valido => const Color(0xff0ca30c);

  Color get rejilla =>
      oscuro ? const Color(0xff2f3a4a) : const Color(0xffdfe3e8);
  Color get eje => oscuro ? const Color(0xff7c8899) : const Color(0xff64748b);
  Color get texto => oscuro ? const Color(0xffc3c2b7) : const Color(0xff52514e);
}

/// Marco, rejilla, marcas numeradas y nombres de eje.
class Ejes {
  const Ejes({
    required this.rect,
    required this.minX,
    required this.maxX,
    required this.minY,
    required this.maxY,
    required this.paleta,
    this.divisiones = 4,
  });

  final Rect rect;
  final double minX, maxX, minY, maxY;
  final VizPalette paleta;
  final int divisiones;

  double x(double v) => rect.left + ((v - minX) / (maxX - minX)) * rect.width;
  double y(double v) => rect.bottom - ((v - minY) / (maxY - minY)) * rect.height;

  /// Margen que hay que reservar para que quepan marcas y nombres.
  static const double margenIzq = 56.0;
  static const double margenAbajo = 48.0;
  static const double margenArriba = 14.0;
  static const double margenDer = 14.0;

  static Rect areaDe(Size size) => Rect.fromLTWH(
        margenIzq,
        margenArriba,
        math.max(1, size.width - margenIzq - margenDer),
        math.max(1, size.height - margenArriba - margenAbajo),
      );

  void dibujar(Canvas canvas, {required String tituloX, required String tituloY}) {
    final rejilla = Paint()
      ..color = paleta.rejilla
      ..strokeWidth = 1;

    for (var i = 0; i <= divisiones; i++) {
      final f = i / divisiones;
      final px = rect.left + rect.width * f;
      final py = rect.bottom - rect.height * f;
      canvas.drawLine(Offset(px, rect.top), Offset(px, rect.bottom), rejilla);
      canvas.drawLine(Offset(rect.left, py), Offset(rect.right, py), rejilla);

      _texto(canvas, _fmt(minX + (maxX - minX) * f),
          Offset(px, rect.bottom + 6), alineacion: TextAlign.center);
      _texto(canvas, _fmt(minY + (maxY - minY) * f),
          Offset(rect.left - 8, py - 6), alineacion: TextAlign.right);
    }

    canvas.drawRect(
      rect,
      Paint()
        ..color = paleta.eje
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );

    _texto(canvas, tituloX,
        Offset(rect.center.dx, rect.bottom + 26),
        alineacion: TextAlign.center, negrita: true);

    // El nombre del eje Y va girado, como en cualquier gráfica científica.
    canvas.save();
    canvas.translate(14, rect.center.dy);
    canvas.rotate(-math.pi / 2);
    _texto(canvas, tituloY, Offset.zero,
        alineacion: TextAlign.center, negrita: true);
    canvas.restore();
  }

  String _fmt(double v) {
    final a = v.abs();
    if (a >= 100) return v.toStringAsFixed(0);
    if (a >= 10) return v.toStringAsFixed(1);
    return v.toStringAsFixed(2);
  }

  void _texto(Canvas canvas, String s, Offset donde,
      {TextAlign alineacion = TextAlign.left, bool negrita = false}) {
    final tp = TextPainter(
      text: TextSpan(
        text: s,
        style: TextStyle(
          color: paleta.texto,
          fontSize: 10.5,
          fontWeight: negrita ? FontWeight.w600 : FontWeight.w400,
        ),
      ),
      textDirection: TextDirection.ltr,
      textAlign: alineacion,
    )..layout();

    final dx = switch (alineacion) {
      TextAlign.center => donde.dx - tp.width / 2,
      TextAlign.right => donde.dx - tp.width,
      _ => donde.dx,
    };
    tp.paint(canvas, Offset(dx, donde.dy));
  }
}

/// Entrada de leyenda: identidad que no depende solo del color.
class ItemLeyenda {
  const ItemLeyenda(this.etiqueta, this.color, {this.relleno = true, this.linea = false});

  final String etiqueta;
  final Color color;
  final bool relleno;
  final bool linea;
}

class Leyenda extends StatelessWidget {
  const Leyenda(this.items, {super.key});

  final List<ItemLeyenda> items;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 14,
      runSpacing: 4,
      children: [
        for (final it in items)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              CustomPaint(
                size: const Size(14, 14),
                painter: _MarcaLeyenda(it),
              ),
              const SizedBox(width: 5),
              // El texto lleva tinta de texto, no el color de la serie: la
              // marca de al lado ya carga la identidad.
              Text(it.etiqueta, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
      ],
    );
  }
}

class _MarcaLeyenda extends CustomPainter {
  const _MarcaLeyenda(this.item);

  final ItemLeyenda item;

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final p = Paint()..color = item.color;
    if (item.linea) {
      p.strokeWidth = 2;
      canvas.drawLine(Offset(0, c.dy), Offset(size.width, c.dy), p);
    } else if (item.relleno) {
      canvas.drawCircle(c, 4.5, p);
    } else {
      canvas.drawCircle(c, 4.2, p..style = PaintingStyle.stroke..strokeWidth = 1.8);
    }
  }

  @override
  bool shouldRepaint(covariant _MarcaLeyenda old) => old.item != item;
}
