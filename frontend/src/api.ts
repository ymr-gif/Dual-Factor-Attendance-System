// API client (Step 12–13). Operator token (if set) is stored in localStorage
// and sent as X-Operator-Token on REST / ?token= on the WebSocket.

const TOKEN_KEY = 'operator_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(t: string): void {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}

async function req<T>(path: string): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['X-Operator-Token'] = token
  const res = await fetch(path, { headers })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function reqJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['X-Operator-Token'] = token
  const res = await fetch(path, { method, headers, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function del<T>(path: string): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['X-Operator-Token'] = token
  const res = await fetch(path, { method: 'DELETE', headers })
  if (!res.ok) throw new Error(`DELETE ${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function postFormData<T>(path: string, data: FormData): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['X-Operator-Token'] = token
  const res = await fetch(path, { method: 'POST', headers, body: data })
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export async function reqBlob(path: string): Promise<Blob> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['X-Operator-Token'] = token
  const res = await fetch(path, { headers })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.blob()
}

export async function reqText(path: string): Promise<string> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['X-Operator-Token'] = token
  const res = await fetch(path, { headers })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.text()
}

// --- Types ---

export interface TapLog {
  id: number
  uid: string
  student_id: string | null
  student_name?: string | null
  ts: string
  method: string
  status: string | null
  face_score: number | null
  face_match: boolean | null
  liveness_score: number | null
  liveness_pass: boolean | null
}

export interface Student {
  student_id: string
  uid: string
  name: string | null
  guardian_email: string | null
  enrolled?: boolean
  face_consent?: boolean | null
  face_consent_at?: string | null
  embed_model?: string | null
  enrolled_at?: string | null
}

export interface TapEvent {
  type: 'tap'
  student: Student | null
  log: TapLog
  reason?: string | null
}

export interface Health {
  status: string
  db: boolean
}

export interface StatsToday {
  date: string
  total: number
  by_status: Record<string, number>
}

export interface Config {
  face: {
    enabled: boolean
    threshold: number
    det_size: number
    min_face_px: number
    use_gpu: boolean
  }
  liveness: {
    enabled: boolean
    threshold: number | null
  }
  decision: {
    enforce_2fa: boolean
  }
  perception: {
    enabled: boolean
    iou_thresh: number
    max_misses: number
    fps: number
  }
  privacy: {
    consent_required: boolean
    attendance_retention_days: number
    score_retention_days: number
  }
}

export interface AuditEntry {
  id: number
  ts: string
  actor: string | null
  action: string
  target: string | null
  detail: string | null
}

export interface ReviewItem {
  id: number
  log_id: number
  student_id: string | null
  status: string
  reason: string | null
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  resolution: string | null
}

export interface ReviewQueueItem {
  id: number
  log_id: number
  student_id: string | null
  student_name: string | null
  status: string
  reason: string | null
  created_at: string
  uid: string | null
  log_ts: string | null
  method: string | null
  face_score: number | null
  face_match: boolean | null
  liveness_score: number | null
  liveness_pass: boolean | null
}

export interface EnrollResult {
  student_id: string
  frames: { file: string; status: string; reason: string | null }[]
  used: number
  duplicate: { student_id: string; name: string; similarity: number } | null
}

export interface SettingsResponse {
  settings: Record<string, string>
  tunable_keys: string[]
}

export interface AttendanceSummary {
  date: string
  expected: number
  present: { student_id: string; name: string | null; late: boolean }[]
  absent: { student_id: string; name: string | null }[]
  late_count: number
  late_cutoff: string | null
}

export interface AttendanceSession {
  student_id: string
  student_name: string | null
  session_date: string
  check_in: string
  check_out: string | null
  duration_minutes: number | null
}

export interface ReenrollDue {
  reenroll_after_days: number
  current_model: string
  due: { student_id: string; name: string | null; embed_model: string | null; enrolled_at: string | null }[]
}

export interface FaceMatch {
  student_id: string
  name: string | null
  uid: string
  similarity: number
}

// --- Endpoints ---

export const getHealth = () => req<Health>('/health')
export const getConfig = () => req<Config>('/api/config')
export const getStudents = () => req<{ students: Student[] }>('/api/students')
export const getStatsToday = () => req<StatsToday>('/api/stats/today')
export const getAttendance = (params: Record<string, string | number> = {}) => {
  const q = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  ).toString()
  return req<{ logs: TapLog[] }>(`/api/attendance${q ? `?${q}` : ''}`)
}

export const createStudent = (b: { student_id: string; uid: string; name?: string; guardian_email?: string }) =>
  reqJson<Student>('/api/students', 'POST', b)

export const updateStudent = (id: string, b: { uid?: string; name?: string; guardian_email?: string }) =>
  reqJson<Student>(`/api/students/${encodeURIComponent(id)}`, 'PATCH', b)

export const deleteStudent = (id: string) =>
  del<{ erased: string; logs: number; students: number }>(`/api/students/${encodeURIComponent(id)}`)

export const setConsent = (id: string, granted: boolean) =>
  reqJson<{ student_id: string; face_consent: boolean }>(`/api/students/${encodeURIComponent(id)}/consent`, 'POST', { granted })

export const enrollStudent = (id: string, data: FormData) =>
  postFormData<EnrollResult>(`/api/students/${encodeURIComponent(id)}/enroll`, data)

export const getReviewQueue = (limit = 100) =>
  req<{ queue: ReviewQueueItem[] }>(`/api/review?limit=${limit}`)

export const resolveReview = (id: number, resolution: string) =>
  reqJson<{ id: number; log_id: number; student_id: string | null; status: string; resolved_at: string; resolved_by: string; resolution: string }>(
    `/api/review/${id}/resolve`, 'POST', { resolution },
  )

export const getSettings = () => req<SettingsResponse>('/api/settings')

export const setSetting = (key: string, value: string) =>
  reqJson<{ key: string; value: string }>('/api/settings', 'PUT', { key, value })

export const getSummary = (date?: string) =>
  req<AttendanceSummary>(`/api/attendance/summary${date ? `?date=${date}` : ''}`)

export const getSessions = (params: { student_id?: string; date?: string } = {}) => {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v != null && v !== '').map(([k, v]) => [k, v!]),
  ).toString()
  return req<{ sessions: AttendanceSession[] }>(`/api/attendance/sessions${q ? `?${q}` : ''}`)
}

export const getAudit = (limit = 100) =>
  req<{ audit: AuditEntry[] }>(`/api/audit?limit=${limit}`)

export const getReenrollDue = () => req<ReenrollDue>('/api/reenroll-due')

export interface PerceptionState {
  enabled: boolean
  ready: boolean
  reason: string
  n_faces?: number
  face_px?: number
  brightness?: number | null
  min_face_px?: number
  age?: number
}

export const getPerceptionState = () => req<PerceptionState>('/api/perception/state')

export const searchFace = (file: File, k = 5) => {
  const fd = new FormData()
  fd.append('image', file)
  return postFormData<{ matches: FaceMatch[] }>(`/api/search-face?k=${k}`, fd)
}

export async function downloadAttendanceCsv(params: Record<string, string | number> = {}) {
  const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()
  const blob = await reqBlob(`/api/attendance.csv${q ? `?${q}` : ''}`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'attendance.csv'; a.click()
  URL.revokeObjectURL(url)
}
