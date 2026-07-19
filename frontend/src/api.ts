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
