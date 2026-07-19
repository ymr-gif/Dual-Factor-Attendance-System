// Live feed (Step 13) — newest taps stream in with status pills and highlights.

import { type TapEvent } from '../api'

const HIGHLIGHT: Record<string, { border: string; bg: string }> = {
  rejected: { border: '#e53e3e', bg: 'rgba(229,62,62,0.08)' },
  spoof: { border: '#e53e3e', bg: 'rgba(229,62,62,0.08)' },
  mismatch: { border: '#e53e3e', bg: 'rgba(229,62,62,0.08)' },
  flagged: { border: '#d69e2e', bg: 'rgba(214,158,46,0.08)' },
  no_face: { border: '#d69e2e', bg: 'rgba(214,158,46,0.08)' },
  tailgating: { border: '#d69e2e', bg: 'rgba(214,158,46,0.08)' },
}

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

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return new Date(ts).toLocaleDateString()
}

export default function LiveFeed({
  taps,
  connected,
}: {
  taps: TapEvent[]
  connected: boolean
}) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 14, opacity: 0.6 }}>Live Feed</h2>
        <span
          className="pill"
          style={{
            background: connected ? '#1f5c2a' : '#5c4a1f',
            fontSize: 10,
          }}
        >
          {connected ? 'connected' : 'reconnecting...'}
        </span>
      </div>
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {taps.length === 0 ? null : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {taps.map((t) => {
              const status = t.log.status ?? 'unknown'
              const hl = HIGHLIGHT[status]
              return (
                <div
                  key={t.log.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 8px',
                    borderRadius: 4,
                    borderLeft: hl ? `3px solid ${hl.border}` : '3px solid transparent',
                    background: hl?.bg || 'transparent',
                  }}
                >
                  <span
                    className="pill"
                    style={{ background: STATUS_COLORS[status] || '#333', minWidth: 80, textAlign: 'center' }}
                  >
                    {status}
                  </span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.student?.name ?? t.log.uid}
                  </span>
                  {t.log.method && (
                    <span className="pill" style={{ background: '#2a2d37', fontSize: 11, opacity: 0.85 }}>
                      {t.log.method}
                    </span>
                  )}
                  {t.log.face_score != null && (
                    <span style={{ fontSize: 12, opacity: 0.7 }}>
                      face {t.log.face_score.toFixed(2)} {t.log.face_match ? '\u2713' : '\u2717'}
                    </span>
                  )}
                  {t.log.liveness_score != null && (
                    <span style={{ fontSize: 12, opacity: 0.7 }}>
                      live {t.log.liveness_score.toFixed(2)} {t.log.liveness_pass ? '\u2713' : '\u2717'}
                    </span>
                  )}
                  <span style={{ fontSize: 12, opacity: 0.5, whiteSpace: 'nowrap' }}>
                    {timeAgo(t.log.ts)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
      {taps.length === 0 && <p style={{ opacity: 0.4, margin: 0 }}>Waiting for taps...</p>}
    </div>
  )
}
