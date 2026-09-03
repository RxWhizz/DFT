/**
 * Cliente HTTP del monitor.
 *
 * Mismo origen que el backend (FastAPI sirve el SPA), así que la cookie de
 * sesión viaja sola y no hace falta ni CORS ni cabecera Authorization.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  get isUnauthorized() {
    return this.status === 401
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

// ── Tipos (espejo de src/monitor_api/models.py) ──────────────────────────────
// Los de abajo son la superficie cómoda que consume la app. Al final del
// archivo se comprueban contra el esquema OpenAPI real (src/lib/api.d.ts,
// regenerado con `npm run gen:api`), así que si el backend cambia un modelo el
// build del frontend falla en vez de romper en tiempo de ejecución.

export type JobStatusName =
  | 'pending' | 'running' | 'converged' | 'partial' | 'failed'
  | 'stalled' | 'oscillating' | 'stopped' | 'skipped_duplicate' | 'unknown'

export interface JobStatus {
  job_id: string
  formula: string
  status: JobStatusName
  // Opcionales porque en el modelo Pydantic llevan default, así que el esquema
  // OpenAPI no los marca como requeridos (lo verifica _ContratoJobStatus).
  pid?: number | null
  start_time?: string | null
  elapsed_min?: number | null
  mpi_cores?: number | null
}

export interface JobStats extends JobStatus {
  energy_history?: number[]
  fmax_history?: number[]
  scf_iter_history?: number[]
  n_fire_steps?: number
  n_scf_iters?: number
  is_oscillating?: boolean
  stall_minutes?: number | null
  final_energy_ev?: number | null
}

export interface JobPage {
  items: JobStatus[]
  total: number
  limit: number
  offset: number
}

export interface Summary {
  n_pending: number
  n_running: number
  n_converged: number
  n_failed: number
  n_stalled: number
  n_oscillating: number
  n_skipped_duplicate?: number
  total: number
  convergence_rate?: number | null
}

export interface SysMetrics {
  cpu_percent: number
  cpu_per_core: number[]
  ram_used_gb: number
  ram_total_gb: number
  ram_percent: number
  pkg_temps: number[]
  core_temp_max: number
  nvme_temp: number | null
  gpu_temps: number[]
}

export interface PathsInfo {
  frozen: boolean
  bundle_root: string
  data_root: string
  config_dir: string
}

export interface PlatformInfo {
  os: string
  frozen: boolean
  hardware_temps: boolean
  runner_launch: boolean
  // Opcional: lleva default en el modelo Pydantic, así que el esquema OpenAPI
  // no lo marca requerido (lo verifica _ContratoHealth).
  runner_python?: string | null
  auto_advance?: boolean
}

export interface Health {
  ok: boolean
  version: string
  paths: PathsInfo
  platform: PlatformInfo
  runs_dir: string
  runs_mounted: boolean
  nearest_existing_path: string
  n_jobs_tracked: number
  last_poll_at: number | null
  last_poll_age_sec: number | null
  poll_interval_sec: number
  ws_clients: number
}

export interface ScfPoint {
  iter: number
  clock: string
  energy: number
  eigst: number | null
  dens: number | null
}

export interface TraceLabel {
  label: string
  path: string
  n_iters: number
  rate_s_per_iter: number | null
  points: ScfPoint[]
}

export interface Frame {
  label: string
  config_index: number | null
  status: string | null
  energy_ev: number | null
  energy_per_atom_ev: number | null
  forces_max_eva: number | null
  n_atoms: number | null
  kpts: number[] | null
  elapsed_s: number | null
  finished_at: string | null
}

export interface JobTraces {
  labels: TraceLabel[]
  frames: Frame[]
}

export interface JobLog {
  label: string | null
  path?: string
  lines: string[]
  total_lines: number
  available: string[]
}

export interface JobMetadata {
  metadata: Record<string, unknown>
  status: Record<string, unknown>
  artifacts: string[]
}

export interface ScreeningTierInfo {
  tier: number
  name: string
  enabled: boolean
  available: boolean
  reason: string | null
  cost_hint: string
}

export interface ScreeningGates {
  goldschmidt: { min: number; max: number }
  octahedral: { min: number; max: number }
  volume_A3: { min: number; max: number }
  pv_window: number[]
  eform_max_eV_atom: number
  beta: number
  n_dft_per_batch: number
  batch_size: number
  chemical_space: { A: string[]; B: string[]; X: string[] }
}

export interface ScreeningConfig {
  available: boolean
  reason: string | null
  tiers: ScreeningTierInfo[]
  gates: ScreeningGates | null
}

export interface FunnelTier {
  tier: number
  name: string
  kind: 'gate' | 'signal' | 'select'
  n_in: number
  n_out: number
  n_dropped: number
  note: string
  seconds: number | null
  ran: boolean
}

export interface ScreeningDrop {
  formula: string | null
  dropped_at_tier: number
  drop_reason: string | null
}

export interface ScreeningItem {
  candidate_id: string | null
  formula: string | null
  generation_mode: string | null
  tolerance_t: number | null
  oct_factor: number | null
  vol_est_A3: number | null
  Eg_surrogate_eV: number | null
  Eg_sigma_eV: number | null
  band_score: number | null
  in_pv_window: boolean | null
  Eform_eV_atom: number | null
  is_stable: boolean | null
  stab_score: number | null
  ucb_bonus: number | null
  total_score: number | null
  passed_eform: boolean | null
  tier_reached: number | null
  dropped_at_tier: number | null
  drop_reason: string | null
}

export interface ScreeningRun {
  run_id: string
  batch_id: number
  n_requested: number
  random_seed: number
  n_batches: number
  n_candidates_per_batch: number
  lot_ids: number[]
  use_mlff: boolean
  status: 'pending' | 'running' | 'done' | 'error'
  stage: string
  started_at: number
  elapsed_sec: number
  error: string | null
  tiers: FunnelTier[]
  n_selected: number
  selected_candidate_ids?: string[]
  dft_batch_path?: string | null
  dft_prepared?: number | null
  dft_started_at?: number | null
  items?: ScreeningItem[]
  dropped?: ScreeningDrop[]
  n_items_total?: number
}

export interface ScreeningStartDftResult {
  run_id: string
  batch_id: number
  batch_path: string
  n_selected: number
  n_prepared: number
  n_existing_or_skipped: number
  runner_launched: boolean
  runner_kind: string
  runner_error?: string | null
}

export interface DiscoveryCandidate {
  candidate_id?: string | null
  formula?: string | null
  generation_mode?: string | null
  B_family?: string | null
  dominant_halide?: string | null
  status?: string | null
  Eg_surrogate_eV?: number | null
  Eg_sigma_eV?: number | null
  Eform_eV_atom?: number | null
  meff_e_pred_m0?: number | null
  meff_h_pred_m0?: number | null
  eps_inf_pred?: number | null
  pv_score_ml?: number | null
  acquisition_score?: number | null
  band_score?: number | null
  stab_score?: number | null
  transport_score?: number | null
  dielectric_score?: number | null
  round_selected?: number | string | null
}

export interface DiscoveryStatus {
  state: {
    status: string
    current_round?: number
    stop_reason?: string | null
    last_screening?: Record<string, unknown>
    last_finalize?: Record<string, unknown>
    space?: Record<string, unknown>
    paths?: Record<string, string>
    /** Presente si la última criba corrió sin Tier 2 por falta del entorno MLFF. */
    mlff_warning?: { error: string; remediation: string } | null
  }
  counts: Record<string, number>
  coverage: { total: number; seen: number; percent: number }
  frontier: DiscoveryCandidate[]
  queue: DiscoveryCandidate[]
  paths: Record<string, string>
  background?: { running: boolean; last_error?: string | null }
}

export interface DiscoveryExport {
  report: string
  ledger: string
  frontier: string
}

export interface Candidate {
  candidate_id: string | null
  formula: string | null
  generation_mode: string | null
  tolerance_t: number | null
  oct_factor: number | null
  vol_est_A3: number | null
  score: number | null
  b_family: string | null
  dominant_halide: string | null
  n_atoms?: number | null
  lattice_constant_A?: number | null
  has_dft: boolean
  dft_status?: string | null
}

export interface CandidatePage {
  items: Candidate[]
  total: number
  limit: number
  offset: number
  source: string
  filters: { goldschmidt: { min: number; max: number }; octahedral: { min: number; max: number } }
  facets: { generation_mode: string[]; b_family: string[]; dominant_halide: string[] }
}

export interface Prediction {
  material: string
  A: string
  B: string
  X: string
  bandgap_pred: number
  bandgap_uncertainty: number
  stability_score: number
  solar_score: number
  in_pv_window: boolean
  model_name: string
  features_used: string[]
}

export interface Top8Row {
  material: string
  A: string
  B: string
  X: string
  Eg_dft_eV?: number
  Eg_exp_eV?: number
  Eg_ml_eV?: number
  Eg_ml_std_eV?: number
  solar_score?: number
  in_pv_window?: boolean
  error?: string
}

export interface ModelInfo {
  name: string
  metrics: Record<string, unknown>
  has_pickle: boolean
  size_mb: number | null
}

export interface ModelsResponse {
  models: ModelInfo[]
  surrogate_status: 'ok' | 'error'
  surrogate_error: string | null
}

export interface CandidatesQuery {
  q?: string
  generation_mode?: string
  b_family?: string
  halide?: string
  sort?: 'score' | 'formula' | 'tolerance_t' | 'oct_factor'
  desc?: boolean
  limit?: number
  offset?: number
}

export interface Batch {
  batch_id: number
  name: string
  path: string
  counts: Record<string, number>
  total: number
  is_current: boolean
  runner_launched: boolean
  rate_per_hour: number | null
  eta_sec: number | null
  n_pending: number
}

export interface StructureRef {
  id: string
  name: string
  group: 'recientes' | 'fases' | 'top8' | 'jobs'
  format: string
  detail?: string | null
  mtime?: number | null
}

export interface StructureContent {
  id: string
  name: string
  format: string
  content: string
  metadata?: Record<string, unknown>
}

export interface ReportDoc {
  path: string
  name: string
  group: string
  size_bytes: number
}

export interface Gallery {
  name: string
  calculation_dir: string | null
  figures: { path: string; name: string; present: boolean }[]
  n_declared: number
  n_present: number
}

export interface ReportsResponse {
  documents: ReportDoc[]
  galleries: Gallery[]
}

export interface MetricsSample {
  t: number
  cpu_percent: number
  ram_percent: number
  ram_used_gb: number
  core_temp_max: number
  gpu_temp_max: number | null
}

export interface MetricsHistory {
  samples: MetricsSample[]
  interval_sec: number
}

export interface AuthState {
  authenticated: boolean
  auth_enabled: boolean
}

export interface AgentHealth {
  enabled: boolean
  provider: string
  ok: boolean
  base_url: string
  model: string
  model_present?: boolean
  manage_service: boolean
  allow_writes?: boolean
  models_dir: string
  revive_repo: string
  version?: string | null
  error?: string | null
}

export interface AgentMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
}

export interface AgentToolResult {
  name: string
  arguments?: Record<string, unknown>
  ok: boolean
  data?: unknown
  error?: string | null
  status_code?: number | null
}

export interface AgentChatResponse {
  ok: boolean
  model: string
  message: string
  structured?: Record<string, unknown> | null
  tool_rounds: number
  tool_results: AgentToolResult[]
  proposal_ids?: string[]
}

export interface AgentProposal {
  id: string
  title: string
  created_at: number
  status: string
  command?: string | null
  diff?: string | null
  rationale?: string | null
  metadata?: Record<string, unknown>
  executed: boolean
}

export interface JobsQuery {
  status?: string
  q?: string
  sort?: 'formula' | 'job_id' | 'status' | 'elapsed_min'
  desc?: boolean
  limit?: number
  offset?: number
}

// ── Wizard de entorno ────────────────────────────────────────────────────────

export interface SetupCapability {
  id: string
  titulo: string
  ok: boolean
  requerido: boolean
  detalle: { versiones?: Record<string, string>; [k: string]: unknown }
  error: string | null
  remediacion: string
  comando: string | null
}

export interface SetupJob {
  running: boolean
  status?: string
  target?: string
  error?: string | null
  log: string[]
}

export interface SetupStatus {
  status: 'ok' | 'degradado' | 'error'
  ok: boolean
  plataforma: string
  python: string
  executable: string
  frozen: boolean
  capacidades: SetupCapability[]
  job: SetupJob
}

export interface SetupPlanStep {
  name: string
  descripcion: string
  comando: string
  opcional: boolean
}

export interface SetupPlan {
  target: string
  steps: SetupPlanStep[]
  notas: string[]
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export const api = {
  me: () => request<AuthState>('/auth/me'),
  login: (token: string) =>
    request<AuthState>('/auth/login', { method: 'POST', body: JSON.stringify({ token }) }),
  logout: () => request<AuthState>('/auth/logout', { method: 'POST' }),

  health: () => request<Health>('/api/health'),
  agentHealth: () => request<AgentHealth>('/api/agent/health'),
  agentChat: (body: {
    message: string
    history?: AgentMessage[]
    job_id?: string | null
    structured?: boolean
  }) => request<AgentChatResponse>('/api/agent/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  approveAgentProposal: (id: string) =>
    request<AgentProposal>(`/api/agent/proposals/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
    }),
  rejectAgentProposal: (id: string) =>
    request<AgentProposal>(`/api/agent/proposals/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
    }),
  summary: () => request<Summary>('/api/summary'),
  system: () => request<SysMetrics>('/api/system'),
  systemHistory: (minutes = 10) =>
    request<MetricsHistory>(`/api/system/history${qs({ minutes })}`),

  jobs: (params: JobsQuery = {}) => request<JobPage>(`/api/jobs${qs({ ...params })}`),
  job: (id: string) => request<JobStats>(`/api/jobs/${encodeURIComponent(id)}`),
  jobStats: (id: string) => request<JobStats>(`/api/jobs/${encodeURIComponent(id)}/stats`),
  converged: (limit = 50) => request<JobStatus[]>(`/api/jobs/converged${qs({ limit })}`),
  jobTraces: (id: string) => request<JobTraces>(`/api/jobs/${encodeURIComponent(id)}/traces`),
  jobLog: (id: string, label?: string, tail = 200) =>
    request<JobLog>(`/api/jobs/${encodeURIComponent(id)}/log${qs({ label, tail })}`),
  jobMetadata: (id: string) =>
    request<JobMetadata>(`/api/jobs/${encodeURIComponent(id)}/metadata`),

  batches: () =>
    request<{ items: Batch[]; root: string; runner_kind: string }>('/api/batches'),
  startBatch: (id: number) =>
    request<{ batch_id: number; launched: boolean; runner_kind: string }>(
      `/api/batches/${id}/start`,
      { method: 'POST' },
    ),
  killJob: (id: string) =>
    request<{ job_id: string; killed_pids: number[]; status: string }>(
      `/api/jobs/${encodeURIComponent(id)}/kill`,
      { method: 'POST' },
    ),
  retryJob: (id: string) =>
    request<{ job_id: string; status: string; requeue_count: number }>(
      `/api/jobs/${encodeURIComponent(id)}/retry`,
      { method: 'POST' },
    ),

  structures: () => request<{ items: StructureRef[] }>('/api/structures'),
  structureContent: (id: string) =>
    request<StructureContent>(`/api/structures/content${qs({ id })}`),

  reports: () => request<ReportsResponse>('/api/reports'),
  reportDocument: (path: string) =>
    request<{ path: string; name: string; content: string }>(
      `/api/reports/document${qs({ path })}`,
    ),
  figureUrl: (path: string) => `/api/reports/figure${qs({ path })}`,

  screeningConfig: () => request<ScreeningConfig>('/api/screening/config'),
  screeningRun: (body: {
    batch_id?: number | null
    n_candidates: number
    n_batches?: number
    random_seed?: number | null
    use_mlff?: boolean | null
  }) =>
    request<ScreeningRun>('/api/screening/run', { method: 'POST', body: JSON.stringify(body) }),
  screeningRuns: () => request<{ items: ScreeningRun[] }>('/api/screening/runs'),
  screeningRunDetail: (id: string, limit = 200) =>
    request<ScreeningRun>(`/api/screening/runs/${encodeURIComponent(id)}${qs({ limit })}`),
  screeningStartDft: (id: string, body: { start_runner?: boolean } = {}) =>
    request<ScreeningStartDftResult>(
      `/api/screening/runs/${encodeURIComponent(id)}/start-dft`,
      {
        method: 'POST',
        body: JSON.stringify({ start_runner: body.start_runner ?? true }),
      },
    ),

  discoveryStatus: () => request<DiscoveryStatus>('/api/discovery/status'),
  discoveryInit: (body: { reset?: boolean } = {}) =>
    request<DiscoveryStatus>('/api/discovery/init', {
      method: 'POST',
      body: JSON.stringify({ reset: body.reset ?? false }),
    }),
  discoveryRun: (body: {
    start_runner?: boolean
    dry_run?: boolean
    use_mlff?: boolean | null
    max_rounds?: number | null
  } = {}) =>
    request<DiscoveryStatus>('/api/discovery/run', {
      method: 'POST',
      body: JSON.stringify({
        start_runner: body.start_runner ?? true,
        dry_run: body.dry_run ?? false,
        use_mlff: body.use_mlff ?? null,
        max_rounds: body.max_rounds ?? null,
      }),
    }),
  discoveryPause: () =>
    request<DiscoveryStatus>('/api/discovery/pause', { method: 'POST' }),
  discoveryResume: () =>
    request<DiscoveryStatus>('/api/discovery/resume', { method: 'POST' }),
  discoveryFrontier: (limit = 100) =>
    request<{ items: DiscoveryCandidate[] }>(`/api/discovery/frontier${qs({ limit })}`),
  discoveryExport: () =>
    request<DiscoveryExport>('/api/discovery/export', { method: 'POST' }),

  candidates: (params: CandidatesQuery = {}) =>
    request<CandidatePage>(`/api/candidates${qs({ ...params })}`),

  models: () => request<ModelsResponse>('/api/models'),
  predict: (body: {
    A: string
    B: string
    X: string
    a_lat?: number | null
    band_gap_gga_ev?: number | null
    eform_ev_atom?: number | null
  }) => request<Prediction>('/api/ml/predict', { method: 'POST', body: JSON.stringify(body) }),
  top8: () => request<{ items: Top8Row[] }>('/api/ml/top8'),

  statusfull: () =>
    request<{ messages: string[]; count: number; timestamp: string }>('/api/statusfull'),

  // `fast` omite la sonda MLFF, que lanza un proceso y tarda segundos.
  setupStatus: (fast = false) => request<SetupStatus>(`/api/setup/status${qs({ fast })}`),
  setupPlan: (target: string, cuda = false) =>
    request<SetupPlan>('/api/setup/plan', {
      method: 'POST',
      body: JSON.stringify({ target, cuda }),
    }),
  setupInstall: (target: string, opts: { cuda?: boolean; recreate?: boolean } = {}) =>
    request<SetupJob>('/api/setup/install', {
      method: 'POST',
      body: JSON.stringify({ target, cuda: false, recreate: false, ...opts }),
    }),
  setupJob: () => request<SetupJob>('/api/setup/job'),
}


// ── Comprobación de contrato contra el OpenAPI ───────────────────────────────
// Puramente de tipos: no genera nada en el bundle.

import type { components } from './api.d'

type Schema = components['schemas']
type Assert<T extends true> = T
/** Lo que manda el servidor tiene que encajar en el tipo que usa la app. */
type Encaja<Servidor, App> = Servidor extends App ? true : false

export type _ContratoJobStatus = Assert<Encaja<Schema['JobStatus'], JobStatus>>
export type _ContratoJobStats = Assert<Encaja<Schema['StatsResponse'], JobStats>>
export type _ContratoJobPage = Assert<Encaja<Schema['JobPage'], JobPage>>
export type _ContratoSummary = Assert<Encaja<Schema['SummaryResponse'], Summary>>
export type _ContratoHealth = Assert<Encaja<Schema['HealthResponse'], Health>>
export type _ContratoSystem = Assert<Encaja<Schema['SysMetricsResponse'], SysMetrics>>
export type _ContratoAuth = Assert<Encaja<Schema['AuthState'], AuthState>>
export type _ContratoAgentHealth = Assert<Encaja<Schema['AgentHealthResponse'], AgentHealth>>
export type _ContratoAgentChat = Assert<Encaja<Schema['AgentChatResponse'], AgentChatResponse>>
