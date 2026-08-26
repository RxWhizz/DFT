import 'package:dft_monitor_flutter/src/structures/cif_parser.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses ASE-style fractional CIF', () {
    const cif = '''
data_test
_cell_length_a 6
_cell_length_b 6
_cell_length_c 6
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Cs1 Cs 0 0 0
Pb1 Pb 0.5 0.5 0.5
I1 I 0.5 0.5 0
''';

    final structure = parseCif(cif);

    expect(structure.atoms, hasLength(3));
    expect(structure.atoms[1].symbol, 'Pb');
    expect(structure.atoms[1].position.x, closeTo(3, 1e-9));
  });
}
