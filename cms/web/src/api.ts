// API của CMS. Tên người thao tác lưu ở trình duyệt, gửi kèm mọi request (header X-Actor) để ghi nhật ký.
export const actorStore = {
  get: () => { try { return localStorage.getItem('cms.actor') || '' } catch { return '' } },
  set: (v: string) => { try { localStorage.setItem('cms.actor', v) } catch { /* bỏ qua */ } },
}

export async function req<T>(url: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(url, { ...init, headers: { 'Content-Type': 'application/json', 'X-Actor': encodeURIComponent(actorStore.get()), ...(init.headers || {}) } })
  const text = await r.text()
  const body = text ? JSON.parse(text) : null
  if (!r.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `Lỗi ${r.status}`)
  return body as T
}
const post = <T,>(url: string, b: unknown = {}) => req<T>(url, { method: 'POST', body: JSON.stringify(b) })
const put = <T,>(url: string, b: unknown) => req<T>(url, { method: 'PUT', body: JSON.stringify(b) })

export type Stats = { procedures: number; rows: number; rows_with_questions: number; questions_pct: number | null; need_review: number; approved: number
  removed: number; last_import: Import | null }
export type Province = { code: string; display: string; short: string; ubnd: string; in_phrase: string; center_address: string; file_prefix: string
  auto: number; with_conditions: number; updated_by: string | null; updated_at: string | null; stats?: Stats | null }
export type Import = { id: number; province: string; source: string; fetched_at: string | null; at: string; actor: string; procedures: number; rows: number
  added: number; changed: number; removed: number; note: string | null }
export type Proc = { province: string; fid: string; uri: string; code: string; name: string; category: string; type: string; levels: string; status: 'ACTIVE' | 'REMOVED'
  change: 'NEW' | 'CHANGED' | 'SAME' | 'REMOVED'; review: 'NEED_REVIEW' | 'APPROVED'; reviewed_by: string | null; reviewed_at: string | null; n_rows: number; n_q: number }
export type Row = { seq: number; title: string; content: string; questions: string | null; tags: string | null }
export type ProcDetail = Proc & { rows: Row[]; history: { at: string; actor: string; action: string; detail: string }[] }
export type Job = { id: string; province: string; status: 'RUNNING' | 'SUCCEEDED' | 'FAILED'; started: string; finished: string | null; actor: string; raw: string
  result: (Import & { trial?: undefined }) | { trial: true; procedures: number; failures: number } | null; error: string | null; log_tail?: string }
export type RawFile = { name: string; province: string; size: number; mtime: string; source?: 'tool' | 'cms' }
export type ExportRec = { id: number; province: string; kind: string; at: string; actor: string; file: string; procedures: number; rows: number }
export type Health = { name: string; ok: boolean; detail: string; ms: number }
export type Audit = { id: number; at: string; actor: string; action: string; province: string | null; fid: string | null; detail: string }
export type Meta = { review: Record<string, string>; change: Record<string, string>; export: Record<string, string> }

export const api = {
  meta: () => req<Meta>('/api/meta'),
  provinces: () => req<{ provinces: Province[]; raws: RawFile[]; jobs: Job[] }>('/api/provinces'),
  province: (c: string) => req<{ province: Province; stats: Stats; categories: string[] }>(`/api/p/${c}`),
  procedures: (c: string, q: Record<string, string | number>) =>
    req<{ total: number; page: number; size: number; items: Proc[] }>(`/api/p/${c}/procedures?${new URLSearchParams(Object.entries(q).map(([k, v]) => [k, String(v)]))}`),
  procedure: (c: string, fid: string) => req<ProcDetail>(`/api/p/${c}/t/${fid}`),
  saveRows: (c: string, fid: string, edits: { seq: number; questions: string; tags: string }[]) =>
    put<{ changed: number; procedure: ProcDetail }>(`/api/p/${c}/t/${fid}/rows`, { edits }),
  suggest: (c: string, fid: string) => post<{ changed: number; procedure: ProcDetail }>(`/api/p/${c}/t/${fid}/suggest`),
  review: (c: string, fid: string, approve: boolean) => post<ProcDetail>(`/api/p/${c}/t/${fid}/review`, { approve }),
  reviewBulk: (c: string, fids: string[]) => post<{ approved: number }>(`/api/p/${c}/review-bulk`, { fids }),
  data: (c: string) => req<{ raws: RawFile[]; imports: Import[]; jobs: Job[]; running: Job | null }>(`/api/p/${c}/data`),
  importRaw: (c: string, file: string) => post<Import>(`/api/p/${c}/import`, { file }),
  collect: (c: string, limit: number) => post<Job>(`/api/p/${c}/collect`, { limit }),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  health: () => req<{ checks: Health[] }>('/api/source-health'),
  exports: (c: string) => req<{ exports: ExportRec[]; stats: Stats; removed: Proc[] }>(`/api/p/${c}/exports`),
  doExport: (c: string, kind: string, only_approved: boolean) => post<ExportRec>(`/api/p/${c}/exports`, { kind, only_approved }),
  saveSettings: (c: string, b: Partial<Province> & { with_conditions?: boolean }) => put<Province>(`/api/p/${c}/settings`, b),
  rebuild: (c: string) => post<Import>(`/api/p/${c}/rebuild`),
  audit: () => req<{ rows: Audit[] }>('/api/audit'),
}

export const fmtNum = (n: number | null | undefined) => (typeof n === 'number' ? n.toLocaleString('vi-VN') : '—')
export const fmtAt = (s: string | null | undefined) => (s ? s.replace('T', ' ').slice(0, 16) : '—')

// ------------------------------------------------------------------ train callbot (docs/01_THIET_KE_TRAIN_BOT.md)
export type TrainStatus = 'DRAFT' | 'SUBMITTED' | 'QUEUED' | 'TRAINING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'
export type TrainSummary = { need_train: number; need_delete: number; synced: number; waiting_review: number; on_bot: number
  active_batch: string | null; last_success: { id: string; status: string; finished_at: string } | null; bot_id: string
  provider: string; mock: boolean; url: string; callback: boolean }
export type TrainEvent = { at: string; status: TrainStatus; progress: number; source: string; message: string }
export type TrainBatch = { id: string; province: string; mode: string; status: TrainStatus; status_vi: string; progress: number; remote_job_id: string | null
  provider: string | null; bot_id: string; upserts: number; deletes: number; rows: number; created_by: string; created_at: string
  submitted_by: string | null; submitted_at: string | null; started_at: string | null; finished_at: string | null; last_update: string | null
  message: string | null; error: string | null; attempt: number; parent_id: string | null; events?: TrainEvent[]
  items?: { fid: string; action: 'UPSERT' | 'DELETE'; name: string; code: string; rows: number }[] }
export type TrainPlan = { upserts: { fid: string; name: string; code: string; first_time: boolean; rows: number }[]
  deletes: { fid: string; name: string; code: string }[]; synced: number; waiting_review: number }

export const trainApi = {
  overview: (c: string) => req<{ summary: TrainSummary; batches: TrainBatch[]; status_vi: Record<string, string> }>(`/api/p/${c}/training`),
  plan: (c: string) => req<TrainPlan>(`/api/p/${c}/training/plan`),
  create: (c: string) => post<TrainBatch>(`/api/p/${c}/training/batches`),
  batch: (id: string) => req<TrainBatch>(`/api/training/batches/${id}`),
  submit: (id: string) => post<TrainBatch>(`/api/training/batches/${id}/submit`),
  refresh: (id: string) => post<TrainBatch>(`/api/training/batches/${id}/refresh`),
  cancel: (id: string) => post<TrainBatch>(`/api/training/batches/${id}/cancel`),
  retry: (id: string) => post<TrainBatch>(`/api/training/batches/${id}/retry`),
}

// ------------------------------------------------------------------ đồng bộ: chạy tay / theo lịch
export type SyncConfig = { province: string; mode: 'MANUAL' | 'SCHEDULE'; scope: 'TRAIN_ONLY' | 'FULL_SYNC'; freq: 'DAILY' | 'WEEKLY' | 'MONTHLY'
  at_time: string; weekday: number; monthday: number; next_run_at: string | null; updated_by: string | null; updated_at: string | null
  mode_vi: string; scope_vi: string; freq_vi: string }
export type SyncRun = { id: number; province: string; trigger: 'MANUAL' | 'SCHEDULE'; scope: string; scope_vi: string; status: string; status_vi: string
  actor: string; started_at: string; finished_at: string | null; import_id: number | null; batch_id: string | null; message: string | null
  steps: { at: string; step: string; ok: boolean; detail: string }[] }
export const syncApi = {
  get: (c: string) => req<{ config: SyncConfig; runs: SyncRun[]; scopes: Record<string, string>; freqs: Record<string, string> }>(`/api/p/${c}/sync`),
  save: (c: string, b: Pick<SyncConfig, 'mode' | 'scope' | 'freq' | 'at_time' | 'weekday' | 'monthday'>) => put<SyncConfig>(`/api/p/${c}/sync`, b),
  run: (c: string, scope?: string) => post<{ run_id: number }>(`/api/p/${c}/sync/run`, { scope: scope ?? null }),
}
