// ignore_for_file: avoid_print
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:dft_monitor_flutter/src/structures/bonds.dart';
import 'package:dft_monitor_flutter/src/structures/cif_parser.dart';

void main() {
  test('CsPbI3 cubico da enlaces Pb-I', () {
    final cif = File('test/_alpha.cif').readAsStringSync();
    final st = parseCif(cif);
    print('atomos: ${st.atoms.length}');
    for (final a in st.atoms) {
      print('  ${a.symbol}  ${a.position}');
    }
    final bonds = detectarEnlaces(st.atoms);
    print('enlaces: ${bonds.length}');
    for (final b in bonds) {
      final d = st.atoms[b.i].position.distanceTo(st.atoms[b.j].position);
      print('  ${st.atoms[b.i].symbol}-${st.atoms[b.j].symbol}  ${d.toStringAsFixed(3)} A');
    }
    expect(bonds, isNotEmpty);
  });
}
