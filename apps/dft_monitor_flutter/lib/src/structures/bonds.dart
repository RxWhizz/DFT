import 'package:vector_math/vector_math_64.dart';

import 'cif_parser.dart';

/// Detección de enlaces para el dibujo de bolas y palos.
///
/// El visor solo pintaba esferas: el estilo «stick» se limitaba a reducir el
/// radio, así que nunca hubo un palo.

/// Radios iónicos efectivos (Å). Los mismos que usa `ml_surrogate.features`
/// para las especies de perovskita, más los ligeros de los cationes orgánicos.
const _radios = <String, double>{
  'H': 0.31, 'C': 0.76, 'N': 0.71, 'O': 0.66,
  'F': 1.33, 'Cl': 1.81, 'Br': 1.96, 'I': 2.20,
  'Li': 0.76, 'Na': 1.02, 'K': 1.38, 'Rb': 1.52, 'Cs': 1.67,
  'Ca': 1.00, 'Sr': 1.18, 'Ba': 1.35,
  'Ge': 0.73, 'Sn': 1.18, 'Pb': 1.19, 'Bi': 1.03, 'Ti': 0.61,
};

const _halogenos = {'F', 'Cl', 'Br', 'I'};
const _alcalinos = {'Li', 'Na', 'K', 'Rb', 'Cs'};
const _ligeros = {'H', 'C', 'N', 'O'};

class Bond {
  const Bond(this.i, this.j);
  final int i;
  final int j;
}

/// Si dos especies deben unirse con un palo.
///
/// En una perovskita ABX3 el armazón son los octaedros B–X. Los contactos
/// A–X son iónicos y a distancia parecida: dibujarlos convierte la celda en una
/// maraña donde no se distingue nada. Por eso los cationes del sitio A quedan
/// fuera, que es como se representa una perovskita en cualquier artículo.
bool _puedenEnlazar(String a, String b) {
  if (_ligeros.contains(a) && _ligeros.contains(b)) return true;   // catión orgánico
  final unoHalogeno = _halogenos.contains(a) ^ _halogenos.contains(b);
  if (!unoHalogeno) return false;
  final otro = _halogenos.contains(a) ? b : a;
  return !_alcalinos.contains(otro);                               // B–X, no A–X
}

/// Enlaces por criterio de distancia, con rejilla espacial.
///
/// Comparar todos contra todos es O(N²): una supercelda 3×3×3 de 40 átomos son
/// 1080 átomos y medio millón de pares en cada fotograma. La rejilla deja el
/// coste proporcional al número de átomos.
List<Bond> detectarEnlaces(
  List<CifAtom> atoms, {
  double tolerancia = 1.15,
  double minimo = 0.4,
}) {
  if (atoms.length < 2) return const [];

  final radios = [
    for (final a in atoms) _radios[a.symbol] ?? 1.4,
  ];
  final corteMax = radios.reduce((a, b) => a > b ? a : b) * 2 * tolerancia;
  if (corteMax <= 0) return const [];

  // Celda de la rejilla = corte máximo: los vecinos posibles están en la
  // propia celda y en las 26 contiguas.
  final celdas = <int, List<int>>{};
  int clave(int x, int y, int z) => (x * 73856093) ^ (y * 19349663) ^ (z * 83492791);
  int idx(double v) => (v / corteMax).floor();

  for (var i = 0; i < atoms.length; i++) {
    final p = atoms[i].position;
    celdas.putIfAbsent(clave(idx(p.x), idx(p.y), idx(p.z)), () => []).add(i);
  }

  final enlaces = <Bond>[];
  for (var i = 0; i < atoms.length; i++) {
    final pi = atoms[i].position;
    final cx = idx(pi.x), cy = idx(pi.y), cz = idx(pi.z);
    for (var dx = -1; dx <= 1; dx++) {
      for (var dy = -1; dy <= 1; dy++) {
        for (var dz = -1; dz <= 1; dz++) {
          final vecinos = celdas[clave(cx + dx, cy + dy, cz + dz)];
          if (vecinos == null) continue;
          for (final j in vecinos) {
            if (j <= i) continue;   // cada par una sola vez
            if (!_puedenEnlazar(atoms[i].symbol, atoms[j].symbol)) continue;
            final d = pi.distanceTo(atoms[j].position);
            final corte = (radios[i] + radios[j]) * tolerancia;
            if (d > minimo && d <= corte) enlaces.add(Bond(i, j));
          }
        }
      }
    }
  }
  return enlaces;
}

/// Punto medio de un enlace, donde cambia el color de cada mitad.
Vector3 medio(Vector3 a, Vector3 b) => (a + b) / 2.0;
