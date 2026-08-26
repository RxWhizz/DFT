class Health {
  const Health({
    required this.ok,
    required this.version,
    required this.dataRoot,
    required this.runsDir,
    required this.runsMounted,
    required this.nJobsTracked,
    required this.lastPollAgeSec,
    required this.wsClients,
    required this.autoAdvance,
  });

  factory Health.fromJson(Map<String, dynamic> json) {
    final paths = Map<String, dynamic>.from(json['paths'] as Map? ?? {});
    return Health(
      ok: json['ok'] == true,
      version: json['version'] as String? ?? '-',
      dataRoot: paths['data_root'] as String? ?? '-',
      runsDir: json['runs_dir'] as String? ?? '-',
      runsMounted: json['runs_mounted'] == true,
      nJobsTracked: (json['n_jobs_tracked'] as num? ?? 0).toInt(),
      lastPollAgeSec: (json['last_poll_age_sec'] as num?)?.toDouble(),
      wsClients: (json['ws_clients'] as num? ?? 0).toInt(),
      autoAdvance:
          Map<String, dynamic>.from(json['platform'] as Map? ?? {})['auto_advance'] ==
              true,
    );
  }

  final bool ok;
  final String version;
  final String dataRoot;
  final String runsDir;
  final bool runsMounted;
  final int nJobsTracked;
  final double? lastPollAgeSec;
  final int wsClients;

  /// Si el monitor puede mutar el pipeline por su cuenta al detectar un lote
  /// acabado (relanzar runner, disparar el orquestador de active learning).
  final bool autoAdvance;
}

class AuthState {
  const AuthState({required this.authenticated, required this.authEnabled});

  factory AuthState.fromJson(Map<String, dynamic> json) {
    return AuthState(
      authenticated: json['authenticated'] == true,
      authEnabled: json['auth_enabled'] == true,
    );
  }

  final bool authenticated;
  final bool authEnabled;
}

class Summary {
  const Summary({
    required this.total,
    required this.pending,
    required this.running,
    required this.converged,
    required this.failed,
    required this.stalled,
    required this.oscillating,
    required this.skippedDuplicate,
    required this.convergenceRate,
  });

  factory Summary.fromJson(Map<String, dynamic> json) {
    return Summary(
      total: (json['total'] as num? ?? 0).toInt(),
      pending: (json['n_pending'] as num? ?? 0).toInt(),
      running: (json['n_running'] as num? ?? 0).toInt(),
      converged: (json['n_converged'] as num? ?? 0).toInt(),
      failed: (json['n_failed'] as num? ?? 0).toInt(),
      stalled: (json['n_stalled'] as num? ?? 0).toInt(),
      oscillating: (json['n_oscillating'] as num? ?? 0).toInt(),
      skippedDuplicate: (json['n_skipped_duplicate'] as num? ?? 0).toInt(),
      convergenceRate: (json['convergence_rate'] as num?)?.toDouble(),
    );
  }

  final int total;
  final int pending;
  final int running;
  final int converged;
  final int failed;
  final int stalled;
  final int oscillating;
  final int skippedDuplicate;
  final double? convergenceRate;
}

class SystemMetrics {
  const SystemMetrics({
    required this.cpuPercent,
    required this.cpuPerCore,
    required this.ramUsedGb,
    required this.ramTotalGb,
    required this.ramPercent,
    required this.gpuTemps,
    required this.coreTempMax,
    this.nvmeTemp,
  });

  factory SystemMetrics.fromJson(Map<String, dynamic> json) {
    return SystemMetrics(
      cpuPercent: (json['cpu_percent'] as num? ?? 0).toDouble(),
      cpuPerCore: [
        for (final value in (json['cpu_per_core'] as List? ?? const []))
          if (value is num) value.toDouble(),
      ],
      ramUsedGb: (json['ram_used_gb'] as num? ?? 0).toDouble(),
      ramTotalGb: (json['ram_total_gb'] as num? ?? 0).toDouble(),
      ramPercent: (json['ram_percent'] as num? ?? 0).toDouble(),
      gpuTemps: [
        for (final value in (json['gpu_temps'] as List? ?? const []))
          if (value is num) value.toDouble(),
      ],
      coreTempMax: (json['core_temp_max'] as num? ?? 0).toDouble(),
      nvmeTemp: (json['nvme_temp'] as num?)?.toDouble(),
    );
  }

  final double cpuPercent;
  final List<double> cpuPerCore;
  final double ramUsedGb;
  final double ramTotalGb;
  final double ramPercent;
  final List<double> gpuTemps;
  final double coreTempMax;
  final double? nvmeTemp;
}

class MetricsSample {
  const MetricsSample({
    required this.t,
    required this.cpuPercent,
    required this.ramPercent,
    required this.ramUsedGb,
    required this.coreTempMax,
    this.gpuTempMax,
  });

  factory MetricsSample.fromJson(Map<String, dynamic> json) {
    return MetricsSample(
      t: (json['t'] as num? ?? 0).toDouble(),
      cpuPercent: (json['cpu_percent'] as num? ?? 0).toDouble(),
      ramPercent: (json['ram_percent'] as num? ?? 0).toDouble(),
      ramUsedGb: (json['ram_used_gb'] as num? ?? 0).toDouble(),
      coreTempMax: (json['core_temp_max'] as num? ?? 0).toDouble(),
      gpuTempMax: (json['gpu_temp_max'] as num?)?.toDouble(),
    );
  }

  final double t;
  final double cpuPercent;
  final double ramPercent;
  final double ramUsedGb;
  final double coreTempMax;
  final double? gpuTempMax;
}

class MetricsHistory {
  const MetricsHistory({required this.samples, required this.intervalSec});

  factory MetricsHistory.fromJson(Map<String, dynamic> json) {
    return MetricsHistory(
      samples: [
        for (final item in (json['samples'] as List? ?? const []))
          MetricsSample.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      intervalSec: (json['interval_sec'] as num? ?? 0).toInt(),
    );
  }

  final List<MetricsSample> samples;
  final int intervalSec;
}

class Job {
  const Job({
    required this.jobId,
    required this.formula,
    required this.status,
    required this.elapsedMin,
    required this.pid,
    required this.mpiCores,
  });

  factory Job.fromJson(Map<String, dynamic> json) {
    return Job(
      jobId: json['job_id'] as String? ?? '',
      formula: json['formula'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      elapsedMin: (json['elapsed_min'] as num?)?.toDouble(),
      pid: (json['pid'] as num?)?.toInt(),
      mpiCores: (json['mpi_cores'] as num?)?.toInt(),
    );
  }

  final String jobId;
  final String formula;
  final String status;
  final double? elapsedMin;
  final int? pid;
  final int? mpiCores;
}

class JobPage {
  const JobPage({required this.items, required this.total});

  factory JobPage.fromJson(Map<String, dynamic> json) {
    return JobPage(
      items: [
        for (final item in (json['items'] as List? ?? const []))
          Job.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      total: (json['total'] as num? ?? 0).toInt(),
    );
  }

  final List<Job> items;
  final int total;
}

class BatchInfo {
  const BatchInfo({
    required this.batchId,
    required this.path,
    required this.counts,
    required this.total,
    required this.isCurrent,
    required this.runnerLaunched,
    required this.nPending,
    this.ratePerHour,
    this.etaSec,
  });

  factory BatchInfo.fromJson(Map<String, dynamic> json) {
    return BatchInfo(
      batchId: (json['batch_id'] as num?)?.toInt() ?? -1,
      path: json['path'] as String? ?? '',
      counts: Map<String, int>.from(
        (json['counts'] as Map? ?? {})
            .map((key, value) => MapEntry('$key', (value as num).toInt())),
      ),
      total: (json['total'] as num? ?? 0).toInt(),
      isCurrent: json['is_current'] == true,
      runnerLaunched: json['runner_launched'] == true,
      nPending: (json['n_pending'] as num? ?? 0).toInt(),
      ratePerHour: (json['rate_per_hour'] as num?)?.toDouble(),
      etaSec: (json['eta_sec'] as num?)?.toDouble(),
    );
  }

  final int batchId;
  final String path;
  final Map<String, int> counts;
  final int total;
  final bool isCurrent;
  final bool runnerLaunched;
  final int nPending;
  final double? ratePerHour;
  final double? etaSec;
}

class StructureItem {
  const StructureItem({
    required this.id,
    required this.name,
    required this.group,
    required this.format,
    this.detail,
    this.mtime,
  });

  factory StructureItem.fromJson(Map<String, dynamic> json) {
    return StructureItem(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      group: json['group'] as String? ?? '',
      format: json['format'] as String? ?? '',
      detail: json['detail'] as String?,
      mtime: (json['mtime'] as num?)?.toDouble(),
    );
  }

  final String id;
  final String name;
  final String group;
  final String format;
  final String? detail;
  final double? mtime;
}

class StructureContent {
  const StructureContent({
    required this.id,
    required this.name,
    required this.content,
    required this.metadata,
  });

  factory StructureContent.fromJson(Map<String, dynamic> json) {
    return StructureContent(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      content: json['content'] as String? ?? '',
      metadata: Map<String, dynamic>.from(json['metadata'] as Map? ?? {}),
    );
  }

  final String id;
  final String name;
  final String content;
  final Map<String, dynamic> metadata;
}

class FunnelTier {
  const FunnelTier({
    required this.tier,
    required this.name,
    required this.kind,
    required this.nIn,
    required this.nOut,
    required this.nDropped,
    required this.ran,
  });

  factory FunnelTier.fromJson(Map<String, dynamic> json) {
    return FunnelTier(
      tier: (json['tier'] as num? ?? 0).toInt(),
      name: json['name'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      nIn: (json['n_in'] as num? ?? 0).toInt(),
      nOut: (json['n_out'] as num? ?? 0).toInt(),
      nDropped: (json['n_dropped'] as num? ?? 0).toInt(),
      ran: json['ran'] != false,
    );
  }

  final int tier;
  final String name;
  final String kind;
  final int nIn;
  final int nOut;
  final int nDropped;
  final bool ran;
}

class ScreeningConfig {
  const ScreeningConfig({
    required this.available,
    required this.reason,
    required this.gates,
  });

  factory ScreeningConfig.fromJson(Map<String, dynamic> json) {
    return ScreeningConfig(
      available: json['available'] == true,
      reason: json['reason'] as String?,
      gates: Map<String, dynamic>.from(json['gates'] as Map? ?? {}),
    );
  }

  final bool available;
  final String? reason;
  final Map<String, dynamic> gates;
}

class ScreeningRun {
  const ScreeningRun({
    required this.runId,
    required this.batchId,
    required this.status,
    required this.stage,
    required this.randomSeed,
    required this.nBatches,
    required this.nRequested,
    required this.nSelected,
    required this.tiers,
    required this.items,
    required this.nItemsTotal,
    this.error,
    this.dftBatchPath,
    this.dftPrepared,
  });

  factory ScreeningRun.fromJson(Map<String, dynamic> json) {
    return ScreeningRun(
      runId: json['run_id'] as String? ?? '',
      batchId: (json['batch_id'] as num? ?? 0).toInt(),
      status: json['status'] as String? ?? 'unknown',
      stage: json['stage'] as String? ?? '',
      randomSeed: (json['random_seed'] as num? ?? 0).toInt(),
      nBatches: (json['n_batches'] as num? ?? 1).toInt(),
      nRequested: (json['n_requested'] as num? ?? 0).toInt(),
      nSelected: (json['n_selected'] as num? ?? 0).toInt(),
      tiers: [
        for (final item in (json['tiers'] as List? ?? const []))
          FunnelTier.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      items: [
        for (final item in (json['items'] as List? ?? const []))
          Map<String, dynamic>.from(item as Map),
      ],
      nItemsTotal: (json['n_items_total'] as num? ??
              (json['items'] as List? ?? const []).length)
          .toInt(),
      error: json['error'] as String?,
      dftBatchPath: json['dft_batch_path'] as String?,
      dftPrepared: (json['dft_prepared'] as num?)?.toInt(),
    );
  }

  final String runId;
  final int batchId;
  final String status;
  final String stage;
  final int randomSeed;
  final int nBatches;
  final int nRequested;
  final int nSelected;
  final List<FunnelTier> tiers;
  final List<Map<String, dynamic>> items;
  final int nItemsTotal;
  final String? error;
  final String? dftBatchPath;
  final int? dftPrepared;
}

class ScreeningStartDftResult {
  const ScreeningStartDftResult({
    required this.runId,
    required this.batchId,
    required this.batchPath,
    required this.nPrepared,
    required this.runnerLaunched,
    this.runnerError,
  });

  factory ScreeningStartDftResult.fromJson(Map<String, dynamic> json) {
    return ScreeningStartDftResult(
      runId: json['run_id'] as String? ?? '',
      batchId: (json['batch_id'] as num? ?? 0).toInt(),
      batchPath: json['batch_path'] as String? ?? '',
      nPrepared: (json['n_prepared'] as num? ?? 0).toInt(),
      runnerLaunched: json['runner_launched'] == true,
      runnerError: json['runner_error'] as String?,
    );
  }

  final String runId;
  final int batchId;
  final String batchPath;
  final int nPrepared;
  final bool runnerLaunched;
  final String? runnerError;
}

class RangeFilter {
  const RangeFilter({required this.min, required this.max});

  factory RangeFilter.fromJson(Map<String, dynamic> json) {
    return RangeFilter(
      min: (json['min'] as num? ?? 0).toDouble(),
      max: (json['max'] as num? ?? 0).toDouble(),
    );
  }

  final double min;
  final double max;
}

class Candidate {
  const Candidate({
    required this.candidateId,
    required this.formula,
    required this.generationMode,
    required this.toleranceT,
    required this.octFactor,
    required this.volumeA3,
    required this.score,
    required this.bFamily,
    required this.dominantHalide,
    required this.hasDft,
    required this.dftStatus,
    this.pvScore,
    this.egPred,
    this.egDft,
    this.batch,
  });

  factory Candidate.fromJson(Map<String, dynamic> json) {
    return Candidate(
      candidateId: json['candidate_id'] as String?,
      formula: json['formula'] as String?,
      generationMode: json['generation_mode'] as String?,
      toleranceT: (json['tolerance_t'] as num?)?.toDouble(),
      octFactor: (json['oct_factor'] as num?)?.toDouble(),
      volumeA3: (json['vol_est_A3'] as num?)?.toDouble(),
      score: (json['score'] as num?)?.toDouble(),
      bFamily: json['b_family'] as String?,
      dominantHalide: json['dominant_halide'] as String?,
      hasDft: json['has_dft'] == true,
      dftStatus: json['dft_status'] as String?,
      pvScore: (json['pv_score'] as num?)?.toDouble(),
      egPred: (json['eg_pred_ev'] as num?)?.toDouble(),
      egDft: (json['eg_dft_ev'] as num?)?.toDouble(),
      batch: json['batch'] as String?,
    );
  }

  /// Cercanía a la ventana fotovoltaica (gaussiana centrada en 1.45 eV).
  final double? pvScore;

  /// Bandgap que predice el modelo a partir de la composición.
  final double? egPred;

  /// Bandgap que dio el DFT, leído del log de GPAW.
  final double? egDft;

  /// Lote del que salió: los candidatos ya no vienen de un único directorio.
  final String? batch;

  final String? candidateId;
  final String? formula;
  final String? generationMode;
  final double? toleranceT;
  final double? octFactor;
  final double? volumeA3;
  final double? score;
  final String? bFamily;
  final String? dominantHalide;
  final bool hasDft;
  final String? dftStatus;
}

class CandidatePage {
  const CandidatePage({
    required this.items,
    required this.total,
    required this.source,
    required this.goldschmidt,
    required this.octahedral,
    required this.facets,
  });

  factory CandidatePage.fromJson(Map<String, dynamic> json) {
    final filters = Map<String, dynamic>.from(json['filters'] as Map? ?? {});
    return CandidatePage(
      items: [
        for (final item in (json['items'] as List? ?? const []))
          Candidate.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      total: (json['total'] as num? ?? 0).toInt(),
      source: json['source'] as String? ?? '-',
      goldschmidt: RangeFilter.fromJson(
        Map<String, dynamic>.from(filters['goldschmidt'] as Map? ?? {}),
      ),
      octahedral: RangeFilter.fromJson(
        Map<String, dynamic>.from(filters['octahedral'] as Map? ?? {}),
      ),
      facets: {
        for (final entry
            in Map<String, dynamic>.from(json['facets'] as Map? ?? {}).entries)
          entry.key: [
            for (final value in (entry.value as List? ?? const [])) '$value'
          ],
      },
    );
  }

  final List<Candidate> items;
  final int total;
  final String source;
  final RangeFilter goldschmidt;
  final RangeFilter octahedral;
  final Map<String, List<String>> facets;
}

class Prediction {
  const Prediction({
    required this.material,
    required this.bandgapPred,
    required this.bandgapUncertainty,
    required this.stabilityScore,
    required this.solarScore,
    required this.inPvWindow,
    required this.modelName,
  });

  factory Prediction.fromJson(Map<String, dynamic> json) {
    return Prediction(
      material: json['material'] as String? ?? '',
      bandgapPred: (json['bandgap_pred'] as num? ?? 0).toDouble(),
      bandgapUncertainty: (json['bandgap_uncertainty'] as num? ?? 0).toDouble(),
      stabilityScore: (json['stability_score'] as num? ?? 0).toDouble(),
      solarScore: (json['solar_score'] as num? ?? 0).toDouble(),
      inPvWindow: json['in_pv_window'] == true,
      modelName: json['model_name'] as String? ?? '-',
    );
  }

  final String material;
  final double bandgapPred;
  final double bandgapUncertainty;
  final double stabilityScore;
  final double solarScore;
  final bool inPvWindow;
  final String modelName;
}

class Top8Row {
  const Top8Row({
    required this.material,
    this.egDft,
    this.egExp,
    this.egMl,
    this.egMlStd,
    this.solarScore,
    this.inPvWindow,
    this.error,
  });

  factory Top8Row.fromJson(Map<String, dynamic> json) {
    return Top8Row(
      material: json['material'] as String? ?? '',
      egDft: (json['Eg_dft_eV'] as num?)?.toDouble(),
      egExp: (json['Eg_exp_eV'] as num?)?.toDouble(),
      egMl: (json['Eg_ml_eV'] as num?)?.toDouble(),
      egMlStd: (json['Eg_ml_std_eV'] as num?)?.toDouble(),
      solarScore: (json['solar_score'] as num?)?.toDouble(),
      inPvWindow: json['in_pv_window'] as bool?,
      error: json['error'] as String?,
    );
  }

  final String material;
  final double? egDft;
  final double? egExp;
  final double? egMl;
  final double? egMlStd;
  final double? solarScore;
  final bool? inPvWindow;
  final String? error;
}

class Top8Response {
  const Top8Response({required this.items});

  factory Top8Response.fromJson(Map<String, dynamic> json) {
    return Top8Response(
      items: [
        for (final item in (json['items'] as List? ?? const []))
          Top8Row.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
    );
  }

  final List<Top8Row> items;
}

class ModelInfo {
  const ModelInfo({
    required this.name,
    required this.metrics,
    required this.hasPickle,
    this.sizeMb,
  });

  factory ModelInfo.fromJson(Map<String, dynamic> json) {
    return ModelInfo(
      name: json['name'] as String? ?? '',
      metrics: Map<String, dynamic>.from(json['metrics'] as Map? ?? {}),
      hasPickle: json['has_pickle'] == true,
      sizeMb: (json['size_mb'] as num?)?.toDouble(),
    );
  }

  final String name;
  final Map<String, dynamic> metrics;
  final bool hasPickle;
  final double? sizeMb;
}

class ModelsResponse {
  const ModelsResponse({
    required this.models,
    required this.surrogateStatus,
    this.surrogateError,
  });

  factory ModelsResponse.fromJson(Map<String, dynamic> json) {
    return ModelsResponse(
      models: [
        for (final item in (json['models'] as List? ?? const []))
          ModelInfo.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      surrogateStatus: json['surrogate_status'] as String? ?? 'unknown',
      surrogateError: json['surrogate_error'] as String?,
    );
  }

  final List<ModelInfo> models;
  final String surrogateStatus;
  final String? surrogateError;
}

class ReportDoc {
  const ReportDoc({
    required this.path,
    required this.name,
    required this.group,
    required this.sizeBytes,
  });

  factory ReportDoc.fromJson(Map<String, dynamic> json) {
    return ReportDoc(
      path: json['path'] as String? ?? '',
      name: json['name'] as String? ?? '',
      group: json['group'] as String? ?? '',
      sizeBytes: (json['size_bytes'] as num? ?? 0).toInt(),
    );
  }

  final String path;
  final String name;
  final String group;
  final int sizeBytes;
}

class ReportFigure {
  const ReportFigure({
    required this.path,
    required this.name,
    required this.present,
  });

  factory ReportFigure.fromJson(Map<String, dynamic> json) {
    return ReportFigure(
      path: json['path'] as String? ?? '',
      name: json['name'] as String? ?? '',
      present: json['present'] == true,
    );
  }

  final String path;
  final String name;
  final bool present;
}

class Gallery {
  const Gallery({
    required this.name,
    required this.figures,
    required this.nDeclared,
    required this.nPresent,
    this.calculationDir,
  });

  factory Gallery.fromJson(Map<String, dynamic> json) {
    return Gallery(
      name: json['name'] as String? ?? '',
      calculationDir: json['calculation_dir'] as String?,
      figures: [
        for (final item in (json['figures'] as List? ?? const []))
          ReportFigure.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      nDeclared: (json['n_declared'] as num? ?? 0).toInt(),
      nPresent: (json['n_present'] as num? ?? 0).toInt(),
    );
  }

  final String name;
  final String? calculationDir;
  final List<ReportFigure> figures;
  final int nDeclared;
  final int nPresent;
}

class ReportsResponse {
  const ReportsResponse({required this.documents, required this.galleries});

  factory ReportsResponse.fromJson(Map<String, dynamic> json) {
    return ReportsResponse(
      documents: [
        for (final item in (json['documents'] as List? ?? const []))
          ReportDoc.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      galleries: [
        for (final item in (json['galleries'] as List? ?? const []))
          Gallery.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
    );
  }

  final List<ReportDoc> documents;
  final List<Gallery> galleries;
}

class ReportDocument {
  const ReportDocument({
    required this.path,
    required this.name,
    required this.content,
  });

  factory ReportDocument.fromJson(Map<String, dynamic> json) {
    return ReportDocument(
      path: json['path'] as String? ?? '',
      name: json['name'] as String? ?? '',
      content: json['content'] as String? ?? '',
    );
  }

  final String path;
  final String name;
  final String content;
}

class AgentHealth {
  const AgentHealth({
    required this.enabled,
    required this.provider,
    required this.ok,
    required this.baseUrl,
    required this.model,
    required this.manageService,
    required this.modelsDir,
    required this.reviveRepo,
    this.modelPresent,
    this.allowWrites,
    this.version,
    this.error,
  });

  factory AgentHealth.fromJson(Map<String, dynamic> json) {
    return AgentHealth(
      enabled: json['enabled'] == true,
      provider: json['provider'] as String? ?? '-',
      ok: json['ok'] == true,
      baseUrl: json['base_url'] as String? ?? '-',
      model: json['model'] as String? ?? '-',
      modelPresent: json['model_present'] as bool?,
      manageService: json['manage_service'] == true,
      allowWrites: json['allow_writes'] as bool?,
      modelsDir: json['models_dir'] as String? ?? '-',
      reviveRepo: json['revive_repo'] as String? ?? '-',
      version: json['version'] as String?,
      error: json['error'] as String?,
    );
  }

  final bool enabled;
  final String provider;
  final bool ok;
  final String baseUrl;
  final String model;
  final bool? modelPresent;
  final bool manageService;
  final bool? allowWrites;
  final String modelsDir;
  final String reviveRepo;
  final String? version;
  final String? error;
}

class AgentToolResult {
  const AgentToolResult({
    required this.name,
    required this.ok,
    this.arguments,
    this.data,
    this.error,
    this.statusCode,
  });

  factory AgentToolResult.fromJson(Map<String, dynamic> json) {
    return AgentToolResult(
      name: json['name'] as String? ?? '',
      ok: json['ok'] == true,
      arguments: Map<String, dynamic>.from(json['arguments'] as Map? ?? {}),
      data: json['data'],
      error: json['error'] as String?,
      statusCode: (json['status_code'] as num?)?.toInt(),
    );
  }

  final String name;
  final bool ok;
  final Map<String, dynamic>? arguments;
  final Object? data;
  final String? error;
  final int? statusCode;
}

class AgentChatResponse {
  const AgentChatResponse({
    required this.ok,
    required this.model,
    required this.message,
    required this.toolRounds,
    required this.toolResults,
    required this.proposalIds,
    this.structured,
  });

  factory AgentChatResponse.fromJson(Map<String, dynamic> json) {
    return AgentChatResponse(
      ok: json['ok'] == true,
      model: json['model'] as String? ?? '',
      message: json['message'] as String? ?? '',
      structured: json['structured'] == null
          ? null
          : Map<String, dynamic>.from(json['structured'] as Map),
      toolRounds: (json['tool_rounds'] as num? ?? 0).toInt(),
      toolResults: [
        for (final item in (json['tool_results'] as List? ?? const []))
          AgentToolResult.fromJson(Map<String, dynamic>.from(item as Map)),
      ],
      proposalIds: [
        for (final value in (json['proposal_ids'] as List? ?? const []))
          '$value'
      ],
    );
  }

  final bool ok;
  final String model;
  final String message;
  final Map<String, dynamic>? structured;
  final int toolRounds;
  final List<AgentToolResult> toolResults;
  final List<String> proposalIds;
}

class AgentProposal {
  const AgentProposal({
    required this.id,
    required this.title,
    required this.status,
    required this.executed,
    this.command,
    this.diff,
    this.rationale,
  });

  factory AgentProposal.fromJson(Map<String, dynamic> json) {
    return AgentProposal(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      status: json['status'] as String? ?? '',
      executed: json['executed'] == true,
      command: json['command'] as String?,
      diff: json['diff'] as String?,
      rationale: json['rationale'] as String?,
    );
  }

  final String id;
  final String title;
  final String status;
  final bool executed;
  final String? command;
  final String? diff;
  final String? rationale;
}


/// Cola de un log de GPAW.
class LogJob {
  const LogJob({
    required this.lineas,
    required this.disponibles,
    required this.total,
    this.etiqueta,
  });

  factory LogJob.fromJson(Map<String, dynamic> json) => LogJob(
        lineas: ((json['lines'] as List?) ?? const []).map((e) => '$e').toList(),
        disponibles:
            ((json['available'] as List?) ?? const []).map((e) => '$e').toList(),
        total: (json['total_lines'] as num? ?? 0).toInt(),
        etiqueta: json['label'] as String?,
      );

  final List<String> lineas;

  /// Ficheros de log del trabajo: `r2scan`, `runner_stdout`, `runner_stderr`.
  final List<String> disponibles;

  final int total;
  final String? etiqueta;
}
