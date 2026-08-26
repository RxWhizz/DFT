/// Un material del lote: lo que predijo el modelo frente a lo que dio el DFT.
class ParityItem {
  const ParityItem({
    required this.formula,
    required this.egDft,
    required this.egPred,
    this.egPredStd,
    this.egPredScissor,
  });

  factory ParityItem.fromJson(Map<String, dynamic> json) => ParityItem(
        formula: json['formula'] as String? ?? '?',
        egDft: (json['eg_dft_ev'] as num).toDouble(),
        egPred: (json['eg_pred_ev'] as num).toDouble(),
        egPredStd: (json['eg_pred_std_ev'] as num?)?.toDouble(),
        egPredScissor: (json['eg_pred_scissor_ev'] as num?)?.toDouble(),
      );

  final String formula;

  /// Bandgap calculado por DFT (PBE), leído del log de GPAW.
  final double egDft;

  /// Bandgap que el predictor da a partir de la composición, sin ver el DFT.
  final double egPred;

  final double? egPredStd;

  /// Predicción tras el desplazamiento rígido que quita el sesgo del modelo.
  final double? egPredScissor;
}

class ParityData {
  const ParityData({
    required this.items,
    required this.nConverged,
    required this.nWithGap,
    this.batch,
    this.error,
    this.scissorEv,
    this.maeRawEv,
    this.maeScissorEv,
    this.nFit = 0,
    this.dftRangeEv,
    this.nDftDistintos = 0,
  });

  factory ParityData.fromJson(Map<String, dynamic> json) => ParityData(
        items: ((json['items'] as List?) ?? const [])
            .whereType<Map>()
            .map((e) => ParityItem.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        nConverged: (json['n_converged'] as num? ?? 0).toInt(),
        nWithGap: (json['n_with_gap'] as num? ?? 0).toInt(),
        batch: json['batch'] as String?,
        error: json['error'] as String?,
        scissorEv: (json['scissor_ev'] as num?)?.toDouble(),
        maeRawEv: (json['mae_raw_ev'] as num?)?.toDouble(),
        maeScissorEv: (json['mae_scissor_ev'] as num?)?.toDouble(),
        nFit: (json['n_fit'] as num? ?? 0).toInt(),
        dftRangeEv: (json['dft_range_ev'] as num?)?.toDouble(),
        nDftDistintos: (json['n_dft_distintos'] as num? ?? 0).toInt(),
      );

  final List<ParityItem> items;
  final int nConverged;
  final int nWithGap;
  final String? batch;
  final String? error;

  /// Desplazamiento rígido ajustado sobre todos los jobs emparejados del lote.
  final double? scissorEv;
  final double? maeRawEv;
  final double? maeScissorEv;
  final int nFit;

  final double? dftRangeEv;
  final int nDftDistintos;

  bool get tieneScissor => scissorEv != null;

  /// Los gaps DFT casi no varían entre materiales: los puntos se apilan y la
  /// gráfica parece tener dos datos. Es un síntoma, no un fallo de dibujo.
  bool get dftDegenerado =>
      items.length > 3 && (dftRangeEv ?? 1) < 0.05;

}
