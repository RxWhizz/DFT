import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:vector_math/vector_math_64.dart';

import 'bonds.dart';
import 'cif_parser.dart';

class CifViewer extends StatefulWidget {
  const CifViewer({
    required this.cif,
    required this.style,
    required this.supercell,
    required this.showCell,
    super.key,
  });

  final String cif;
  final String style;
  final int supercell;
  final bool showCell;

  @override
  State<CifViewer> createState() => _CifViewerState();
}

class _CifViewerState extends State<CifViewer> {
  double _yaw = -0.6;
  double _pitch = 0.55;
  double _zoom = 1.0;

  // El CIF se parseaba en cada `build`, o sea en cada fotograma de rotacion, y
  // los enlaces cuestan mas todavia. Se memorizan y solo se rehacen cuando
  // cambia la estructura o la supercelda.
  String? _cifCache;
  int? _superCache;
  CifStructure? _structure;
  List<CifAtom> _atoms = const [];
  List<Bond> _bonds = const [];
  Object? _parseError;

  void _preparar() {
    if (_cifCache == widget.cif && _superCache == widget.supercell) return;
    _cifCache = widget.cif;
    _superCache = widget.supercell;
    _parseError = null;
    try {
      final st = parseCif(widget.cif);
      _structure = st;
      _atoms = _expandir(st, widget.supercell);
      _bonds = detectarEnlaces(_atoms);
    } catch (error) {
      _parseError = error;
      _structure = null;
      _atoms = const [];
      _bonds = const [];
    }
  }

  static List<CifAtom> _expandir(CifStructure st, int supercell) {
    final atoms = <CifAtom>[];
    for (var i = 0; i < supercell; i++) {
      for (var j = 0; j < supercell; j++) {
        for (var k = 0; k < supercell; k++) {
          final offset = st.va * i.toDouble() +
              st.vb * j.toDouble() +
              st.vc * k.toDouble();
          for (final atom in st.atoms) {
            atoms.add(
                CifAtom(symbol: atom.symbol, position: atom.position + offset));
          }
        }
      }
    }
    return atoms;
  }

  @override
  Widget build(BuildContext context) {
    _preparar();
    final structure = _structure;
    if (structure == null) {
      final error = _parseError;
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: SelectableText('No se pudo parsear el CIF:\n$error\n\n${widget.cif}'),
        ),
      );
    }

    return GestureDetector(
      onPanUpdate: (details) {
        setState(() {
          _yaw += details.delta.dx * 0.01;
          _pitch = (_pitch + details.delta.dy * 0.01).clamp(-1.45, 1.45);
        });
      },
      child: Listener(
        onPointerSignal: (signal) {
          if (signal is PointerScrollEvent) {
            setState(() {
              _zoom = (_zoom * (signal.scrollDelta.dy > 0 ? 0.9 : 1.1)).clamp(0.3, 4.0);
            });
          }
        },
        child: CustomPaint(
          painter: _CifPainter(
            structure: structure,
            atoms: _atoms,
            bonds: _bonds,
            yaw: _yaw,
            pitch: _pitch,
            zoom: _zoom,
            style: widget.style,
            supercell: widget.supercell,
            showCell: widget.showCell,
          ),
          child: const SizedBox.expand(),
        ),
      ),
    );
  }
}

class _CifPainter extends CustomPainter {
  _CifPainter({
    required this.structure,
    required this.atoms,
    required this.bonds,
    required this.yaw,
    required this.pitch,
    required this.zoom,
    required this.style,
    required this.supercell,
    required this.showCell,
  });

  final CifStructure structure;
  final List<CifAtom> atoms;
  final List<Bond> bonds;
  final double yaw;
  final double pitch;
  final double zoom;
  final String style;
  final int supercell;
  final bool showCell;

  @override
  void paint(Canvas canvas, Size size) {
    final bg = Paint()..color = const Color(0xff0a0d12);
    canvas.drawRect(Offset.zero & size, bg);

    final points = <Vector3>[
      for (final atom in atoms) atom.position,
      ...structure.cellCorners(supercell: supercell),
    ];
    final center = points.fold<Vector3>(Vector3.zero(), (a, b) => a + b) / points.length.toDouble();
    final rotated = points.map((p) => _rotate(p - center)).toList();
    final maxRadius = rotated.fold<double>(1, (max, p) => math.max(max, math.max(p.x.abs(), p.y.abs())));
    final scale = math.min(size.width, size.height) * 0.42 * zoom / maxRadius;

    Offset project(Vector3 p) {
      final r = _rotate(p - center);
      return Offset(size.width / 2 + r.x * scale, size.height / 2 - r.y * scale);
    }

    if (showCell) _drawCell(canvas, project);

    // Radio de la bola y grosor del palo por estilo. Antes los tres estilos
    // solo cambiaban el radio: «stick» pintaba bolas pequeñas y ningún palo.
    final (radioBola, grosorPalo) = switch (style) {
      'spacefill' => (8.5, 0.0),          // esferas que se tocan: sin palos
      'stick' => (2.0, 4.0),              // predominan los enlaces
      _ => (5.0, 2.6),                    // bolas y palos
    };

    if (grosorPalo > 0) {
      // Los palos van debajo de las bolas: dibujados encima taparían los
      // átomos y el orden de profundidad dejaría de leerse.
      for (final b in bonds) {
        final pa = atoms[b.i].position;
        final pb = atoms[b.j].position;
        final m = medio(pa, pb);
        final za = ((_rotate(pa - center).z / maxRadius) + 1) / 2;
        final zb = ((_rotate(pb - center).z / maxRadius) + 1) / 2;

        // Cada mitad con el color de su átomo, como en cualquier visor de
        // estructuras: así se ve a qué especie pertenece cada extremo.
        for (final (p, q, color, z) in [
          (pa, m, _elementColor(atoms[b.i].symbol), za),
          (pb, m, _elementColor(atoms[b.j].symbol), zb),
        ]) {
          canvas.drawLine(
            project(p),
            project(q),
            Paint()
              ..color = Color.lerp(
                  color.withValues(alpha: 0.45), color, z.clamp(0, 1))!
              ..strokeWidth = grosorPalo
              ..strokeCap = StrokeCap.round,
          );
        }
      }
    }

    final sorted = atoms.toList()
      ..sort((a, b) => _rotate(a.position - center).z.compareTo(_rotate(b.position - center).z));
    for (final atom in sorted) {
      final r = _rotate(atom.position - center);
      final zShade = ((r.z / maxRadius) + 1) / 2;
      final color = _elementColor(atom.symbol);
      final paint = Paint()
        ..color = Color.lerp(color.withValues(alpha: 0.65), color, zShade.clamp(0, 1))!
        ..style = PaintingStyle.fill;
      canvas.drawCircle(project(atom.position), radioBola, paint);
    }
  }

  void _drawCell(Canvas canvas, Offset Function(Vector3 p) project) {
    final aa = structure.va * supercell.toDouble();
    final bb = structure.vb * supercell.toDouble();
    final cc = structure.vc * supercell.toDouble();
    final corners = [
      Vector3.zero(),
      aa,
      bb,
      cc,
      aa + bb,
      aa + cc,
      bb + cc,
      aa + bb + cc,
    ];
    const edges = [
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 4],
      [1, 5],
      [2, 4],
      [2, 6],
      [3, 5],
      [3, 6],
      [4, 7],
      [5, 7],
      [6, 7],
    ];
    final paint = Paint()
      ..color = const Color(0xff3b82f6)
      ..strokeWidth = 1.2
      ..style = PaintingStyle.stroke;
    for (final edge in edges) {
      canvas.drawLine(project(corners[edge[0]]), project(corners[edge[1]]), paint);
    }
  }

  Vector3 _rotate(Vector3 p) {
    final cy = math.cos(yaw);
    final sy = math.sin(yaw);
    final cp = math.cos(pitch);
    final sp = math.sin(pitch);
    final x1 = p.x * cy - p.z * sy;
    final z1 = p.x * sy + p.z * cy;
    final y2 = p.y * cp - z1 * sp;
    final z2 = p.y * sp + z1 * cp;
    return Vector3(x1, y2, z2);
  }

  Color _elementColor(String symbol) {
    return switch (symbol) {
      'Cs' => const Color(0xfff59e0b),
      'Rb' => const Color(0xfff97316),
      'K' => const Color(0xfffb923c),
      'MA' || 'FA' || 'N' => const Color(0xff22c55e),
      'Pb' => const Color(0xff94a3b8),
      'Sn' => const Color(0xff38bdf8),
      'Ge' => const Color(0xff60a5fa),
      'I' => const Color(0xffa78bfa),
      'Br' => const Color(0xffef4444),
      'Cl' => const Color(0xff86efac),
      'H' => const Color(0xffe5e7eb),
      'C' => const Color(0xff64748b),
      _ => const Color(0xffcbd5e1),
    };
  }

  @override
  bool shouldRepaint(covariant _CifPainter oldDelegate) {
    return structure != oldDelegate.structure ||
        yaw != oldDelegate.yaw ||
        pitch != oldDelegate.pitch ||
        zoom != oldDelegate.zoom ||
        style != oldDelegate.style ||
        supercell != oldDelegate.supercell ||
        showCell != oldDelegate.showCell;
  }
}
