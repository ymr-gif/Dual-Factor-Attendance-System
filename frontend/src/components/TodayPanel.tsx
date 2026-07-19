// Today panel (Step 13) — shows today's tap counts by status.

import { useEffect, useState } from 'react'
import { getStatsToday, type StatsToday } from '../api'

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

export default function TodayPanel({ refreshKey }: { refreshKey?: number }) {
  const [data, setData] = useState<StatsToday | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getStatsToday()
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setErr(String(e)) })
    return () => { cancelled = true }
  }, [refreshKey])

  if (err) return <div style={{ opacity: 0.6 }}>Stats unavailable: {err}</div>
  if (!data) return <div style={{ opacity: 0.4 }}>Loading stats...</div>

  return (
    <div>
      <h2 style={{ margin: '0 0 8px', fontSize: 14, opacity: 0.6 }}>Today</h2>
      <div style={{ fontSize: 36, fontWeight: 700, margin: '0 0 12px' }}>
        {data.total}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {Object.entries(data.by_status).map(([status, count]) => (
          <span
            key={status}
            className="pill"
            style={{ background: STATUS_COLORS[status] || '#333' }}
          >
            {status}: {count}
          </span>
        ))}
        {Object.keys(data.by_status).length === 0 && (
          <span style={{ opacity: 0.4 }}>No taps today</span>
        )}
      </div>
    </div>
  )
}
