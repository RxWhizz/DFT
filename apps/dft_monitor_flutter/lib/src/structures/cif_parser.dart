import 'dart:math' as math;

import 'package:vector_math/vector_math_64.dart';

class CifAtom {
  const CifAtom({required this.symbol, required this.position});

  final String symbol;
  final Vector3 position;
}

class CifStructure {
  const CifStructure({
    required this.a,
    required this.b,
    required this.c,
    required this.alpha,
    required this.beta,
    required this.gamma,
    required this.atoms,
  });

  final double a;
  final double b;
  final double c;
  final double alpha;
  final double beta;
  final double gamma;
  final List<CifAtom> atoms;

  Vector3 get va => Vector3(a, 0, 0);

  Vector3 get vb {
    final g = _rad(gamma);
    return Vector3(b * math.cos(g), b * math.sin(g), 0);
  }

  Vector3 get vc {
    final al = _rad(alpha);
    final be = _rad(beta);
    final ga = _rad(gamma);
    final cx = c * math.cos(be);
    final cy = c * (math.cos(al) - math.cos(be) * math.cos(ga)) / math.sin(ga);
    final cz2 = c * c - cx * cx - cy * cy;
    return Vector3(cx, cy, math.sqrt(math.max(0, cz2)));
  }

  Vector3 fracToCartesian(double x, double y, double z) => va * x + vb * y + vc * z;

  List<Vector3> cellCorners({int supercell = 1}) {
    final aa = va * supercell.toDouble();
    final bb = vb * supercell.toDouble();
    final cc = vc * supercell.toDouble();
    return [
      Vector3.zero(),
      aa,
      bb,
      cc,
      aa + bb,
      aa + cc,
      bb + cc,
      aa + bb + cc,
    ];
  }
}

class CifParseException implements Exception {
  const CifParseException(this.message);
  final String message;

  @override
  String toString() => message;
}

CifStructure parseCif(String cif) {
  final lines = cif
      .split(RegExp(r'\r?\n'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty && !line.startsWith('#'))
      .toList();

  final values = <String, String>{};
  for (final line in lines) {
    if (!line.startsWith('_')) continue;
    final parts = _split(line);
    if (parts.length >= 2) values[parts[0]] = parts[1];
  }

  final a = _number(values['_cell_length_a']);
  final b = _number(values['_cell_length_b']);
  final c = _number(values['_cell_length_c']);
  final alpha = _number(values['_cell_angle_alpha'], fallback: 90);
  final beta = _number(values['_cell_angle_beta'], fallback: 90);
  final gamma = _number(values['_cell_angle_gamma'], fallback: 90);

  if (a <= 0 || b <= 0 || c <= 0) {
    throw const CifParseException('CIF sin parametros de celda validos');
  }

  final shell = CifStructure(
    a: a,
    b: b,
    c: c,
    alpha: alpha,
    beta: beta,
    gamma: gamma,
    atoms: const [],
  );
  final atoms = _parseAtomLoop(lines, shell);
  if (atoms.isEmpty) throw const CifParseException('CIF sin atom_site legible');

  return CifStructure(
    a: a,
    b: b,
    c: c,
    alpha: alpha,
    beta: beta,
    gamma: gamma,
    atoms: atoms,
  );
}

List<CifAtom> _parseAtomLoop(List<String> lines, CifStructure cell) {
  for (var i = 0; i < lines.length; i++) {
    if (lines[i] != 'loop_') continue;
    final tags = <String>[];
    var rowStart = i + 1;
    while (rowStart < lines.length && lines[rowStart].startsWith('_')) {
      tags.add(lines[rowStart]);
      rowStart++;
    }
    if (!tags.any((tag) => tag.startsWith('_atom_site_'))) continue;

    final symIdx = _firstIndex(tags, const [
      '_atom_site_type_symbol',
      '_atom_site_label',
    ]);
    final fx = tags.indexOf('_atom_site_fract_x');
    final fy = tags.indexOf('_atom_site_fract_y');
    final fz = tags.indexOf('_atom_site_fract_z');
    final cx = tags.indexOf('_atom_site_Cartn_x');
    final cy = tags.indexOf('_atom_site_Cartn_y');
    final cz = tags.indexOf('_atom_site_Cartn_z');

    if (symIdx < 0) continue;
    final hasFrac = fx >= 0 && fy >= 0 && fz >= 0;
    final hasCart = cx >= 0 && cy >= 0 && cz >= 0;
    if (!hasFrac && !hasCart) continue;

    final atoms = <CifAtom>[];
    for (var row = rowStart; row < lines.length; row++) {
      final line = lines[row];
      if (line == 'loop_' || line.startsWith('_') || line.startsWith('data_')) break;
      final parts = _split(line);
      if (parts.length < tags.length) continue;
      final symbol = _symbol(parts[symIdx]);
      final position = hasFrac
          ? cell.fracToCartesian(_number(parts[fx]), _number(parts[fy]), _number(parts[fz]))
          : Vector3(_number(parts[cx]), _number(parts[cy]), _number(parts[cz]));
      atoms.add(CifAtom(symbol: symbol, position: position));
    }
    if (atoms.isNotEmpty) return atoms;
  }
  return const [];
}

int _firstIndex(List<String> tags, List<String> candidates) {
  for (final candidate in candidates) {
    final index = tags.indexOf(candidate);
    if (index >= 0) return index;
  }
  return -1;
}

List<String> _split(String line) {
  return RegExp(r'''(?:[^\s'"]+|'[^']*'|"[^"]*")+''')
      .allMatches(line)
      .map((m) => _clean(m.group(0)!))
      .toList();
}

String _clean(String raw) {
  var value = raw.trim();
  if ((value.startsWith("'") && value.endsWith("'")) ||
      (value.startsWith('"') && value.endsWith('"'))) {
    value = value.substring(1, value.length - 1);
  }
  return value;
}

String _symbol(String raw) {
  final match = RegExp(r'[A-Z][a-z]?').firstMatch(raw);
  return match?.group(0) ?? raw;
}

double _number(String? raw, {double fallback = 0}) {
  if (raw == null || raw == '?' || raw == '.') return fallback;
  final cleaned = raw.replaceAll(RegExp(r'\([^)]*\)'), '');
  return double.tryParse(cleaned) ?? fallback;
}

double _rad(double degrees) => degrees * math.pi / 180;
