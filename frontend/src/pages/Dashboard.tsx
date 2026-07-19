// Operator dashboard (Step 13) — live feed, today stats, history table.

import { useCallback, useEffect, useState } from 'react'
import { getHealth, setToken, getToken, type Health, type TapEvent } from '../api'
import { useTapStream } from '../useTapStream'
import TodayPanel from '../components/TodayPanel'
import LiveFeed from '../components/LiveFeed'
import HistoryTable from '../components/HistoryTable'
import CameraFeed from '../components/CameraFeed'

function AuthGate({ onAuth }: { onAuth: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    if (!value.trim()) { setError('Token required'); return }
    setToken(value.trim())
    onAuth()
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 120 }}>
      <div style={{ width: 320 }}>
        <h2 style={{ margin: '0 0 12px', fontSize: 18 }}>Operator Login</h2>
        <input
          type="password"
          placeholder="Enter operator token"
          value={value}
          onChange={(e) => { setValue(e.target.value); setError(null) }}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          style={{
            width: '100%',
            background: '#1c1f27',
            color: '#e6e8ee',
            border: '1px solid #333',
            borderRadius: 4,
            padding: '8px 12px',
            fontSize: 14,
            marginBottom: 8,
          }}
        />
        {error && <p style={{ color: '#e53e3e', margin: '0 0 8px', fontSize: 13 }}>{error}</p>}
        <button
          onClick={submit}
          style={{
            width: '100%',
            background: '#1f5c2a',
            color: '#e6e8ee',
            border: 'none',
            borderRadius: 4,
            padding: '8px 12px',
            fontSize: 14,
            cursor: 'pointer',
          }}
        >
          Enter
        </button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [authed, setAuthed] = useState(() => !!getToken())
  const [health, setHealth] = useState<Health | null>(null)
  const [taps, setTaps] = useState<TapEvent[]>([])
  const [todayKey, setTodayKey] = useState(0)

  const handleTap = useCallback((e: TapEvent) => {
    setTaps((prev) => [e, ...prev].slice(0, 50))
    setTodayKey((k) => k + 1)
  }, [])

  const { connected } = useTapStream(authed ? handleTap : undefined)

  useEffect(() => {
    if (!authed) return
    getHealth().then(setHealth).catch(() => {})
  }, [authed])

  const logout = () => {
    setToken('')
    setAuthed(false)
    setTaps([])
    setHealth(null)
  }

  if (!authed) return <AuthGate onAuth={() => setAuthed(true)} />

  return (
    <div className="wrap">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>nfc-scan</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {health && (
            <span
              className="pill"
              style={{ background: health.db ? '#1f5c2a' : '#5c1f22' }}
            >
              {health.status}
            </span>
          )}
          <button
            onClick={logout}
            style={{
              background: 'transparent',
              color: '#6ea8fe',
              border: '1px solid #333',
              borderRadius: 4,
              padding: '2px 8px',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            logout
          </button>
        </div>
      </div>

      <div className="dash-grid">
        <TodayPanel refreshKey={todayKey} />
        <LiveFeed taps={taps} connected={connected} />
      </div>

      <CameraFeed />

      <HistoryTable refreshKey={todayKey} />
    </div>
  )
}
