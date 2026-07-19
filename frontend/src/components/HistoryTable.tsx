// History table (Step 13) — filterable, paginated attendance log.

import { useEffect, useState } from 'react'
import { getAttendance, type TapLog } from '../api'

const STATUS_COLORS: Record<string, string> = {
  accepted: '#1f5c2a',
  flagged: '#5c4a1f',
  rejected: '#5c1f22',
  spoof: '#5c1f22',
  mismatch: '#5c1f22',
  no_face: '#5c4a1f',
  tailgating: '#5c1f22',
  unverified: '#333',
  unregistered: '#333',
}

const ALL_STATUSES = [
  '', 'accepted', 'flagged', 'rejected', 'unverified', 'unregistered',
  'no_face', 'mismatch', 'spoof', 'tailgating',
]

export default function HistoryTable({ refreshKey }: { refreshKey?: number }) {
  const [logs, setLogs] = useState<TapLog[]>([])
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [status, setStatus] = useState('')
  const [limit, setLimit] = useState(25)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const fetchLogs = () => {
    setLoading(true)
    setErr(null)
    const params: Record<string, string | number> = { limit }
    if (date) params.date = date
    if (status) params.status = status
    getAttendance(params)
      .then((d) => setLogs(d.logs))
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchLogs() }, [date, status, limit, refreshKey])

  return (
    <div>
      <h2 style={{ margin: '0 0 8px', fontSize: 14, opacity: 0.6 }}>History</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <input
          type="date"
          value={date}
          onChange={(e) => { setDate(e.target.value); setLimit(25) }}
          style={{
            background: '#1c1f27',
            color: '#e6e8ee',
            border: '1px solid #333',
            borderRadius: 4,
            padding: '4px 8px',
            fontSize: 13,
          }}
        />
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setLimit(25) }}
          style={{
            background: '#1c1f27',
            color: '#e6e8ee',
            border: '1px solid #333',
            borderRadius: 4,
            padding: '4px 8px',
            fontSize: 13,
          }}
        >
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>{s || 'All statuses'}</option>
          ))}
        </select>
      </div>
      {err && (
        <p style={{ color: '#e53e3e', margin: '0 0 8px' }}>
          Failed to load: {err}{' '}
          <button onClick={fetchLogs} style={{ fontSize: 12, cursor: 'pointer' }}>retry</button>
        </p>
      )}
      {loading && logs.length === 0 ? (
        <p style={{ opacity: 0.4 }}>Loading...</p>
      ) : logs.length === 0 ? (
        <p style={{ opacity: 0.4 }}>No records for this date/filters.</p>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #333', textAlign: 'left' }}>
                  <th style={{ padding: '6px 8px' }}>Time</th>
                  <th style={{ padding: '6px 8px' }}>Student</th>
                  <th style={{ padding: '6px 8px' }}>Status</th>
                  <th style={{ padding: '6px 8px' }}>Face</th>
                  <th style={{ padding: '6px 8px' }}>Liveness</th>
                  <th style={{ padding: '6px 8px' }}>Method</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr
                    key={log.id}
                    style={{ borderBottom: '1px solid #1c1f27' }}
                  >
                    <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                      {new Date(log.ts).toLocaleTimeString()}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      {log.student_name || log.student_id || log.uid}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      <span
                        className="pill"
                        style={{ background: STATUS_COLORS[log.status || ''] || '#333' }}
                      >
                        {log.status || '\u2014'}
                      </span>
                    </td>
                    <td style={{ padding: '6px 8px', fontSize: 12 }}>
                      {log.face_score != null
                        ? `${log.face_score.toFixed(2)} ${log.face_match ? '\u2713' : '\u2717'}`
                        : '\u2014'}
                    </td>
                    <td style={{ padding: '6px 8px', fontSize: 12 }}>
                      {log.liveness_score != null
                        ? `${log.liveness_score.toFixed(2)} ${log.liveness_pass ? '\u2713' : '\u2717'}`
                        : '\u2014'}
                    </td>
                    <td style={{ padding: '6px 8px', fontSize: 12, opacity: 0.6 }}>
                      {log.method}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {logs.length >= limit && (
            <button
              onClick={() => setLimit(limit + 25)}
              style={{
                marginTop: 8,
                background: '#1c1f27',
                color: '#e6e8ee',
                border: '1px solid #333',
                borderRadius: 4,
                padding: '4px 12px',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Load more
            </button>
          )}
        </>
      )}
    </div>
  )
}
