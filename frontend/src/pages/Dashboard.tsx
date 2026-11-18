// Operator dashboard (Step 13). Camera on the left with the scan steps and today's counts
// under it; on the right the History table over the Live Feed (the backend's own log).
// Stacks into one column on a narrow screen (index.css .dash).

import { useCallback, useEffect, useState } from 'react'
import { getHealth, getLogs, getSettings, setToken, getToken, type Health, type LogLine, type StreamEvent } from '../api'
import { useTapStream } from '../useTapStream'
import TodayPanel from '../components/TodayPanel'
import LiveFeed from '../components/LiveFeed'
import HistoryTable from '../components/HistoryTable'
import CameraFeed from '../components/CameraFeed'
import ScanSteps, { useScanSteps } from '../components/ScanSteps'

const MAX_LOG_LINES = 500

function AuthGate({ onAuth }: { onAuth: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  // A saved token used to be trusted on sight (bool-cast of "something is in
  // localStorage"), so a typo looked identical to a successful login and every
  // real API call 401'd silently after. Check it against the backend first.
  const submit = async () => {
    const v = value.trim()
    if (!v) { setError('Token required'); return }
    setToken(v)
    setChecking(true); setError(null)
    try {
      await getSettings()
      window.dispatchEvent(new CustomEvent('auth-changed'))
      onAuth()
    } catch {
      setToken('')
      setError('Invalid token — check for typos and try again')
    } finally {
      setChecking(false)
    }
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
          onKeyDown={(e) => e.key === 'Enter' && !checking && submit()}
          disabled={checking}
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
          disabled={checking}
          style={{
            width: '100%',
            background: '#1f5c2a',
            color: '#e6e8ee',
            border: 'none',
            borderRadius: 4,
            padding: '8px 12px',
            fontSize: 14,
            cursor: checking ? 'default' : 'pointer',
            opacity: checking ? 0.6 : 1,
          }}
        >
          {checking ? 'Checking...' : 'Enter'}
        </button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [authed, setAuthed] = useState(() => !!getToken())
  const [health, setHealth] = useState<Health | null>(null)
  const [lines, setLines] = useState<LogLine[]>([])
  const [todayKey, setTodayKey] = useState(0)
  const { scan, fading, onStage } = useScanSteps()

  const handleTap = useCallback(() => setTodayKey((k) => k + 1), [])

  const handleEvent = useCallback((e: StreamEvent) => {
    if (e.type === 'log') {
      setLines((prev) => (prev.length && prev[prev.length - 1].seq >= e.seq ? prev : [...prev, e].slice(-MAX_LOG_LINES)))
    } else if (e.type === 'stage') {
      onStage(e)
    }
  }, [onStage])

  const { connected } = useTapStream(authed ? handleTap : undefined, authed ? handleEvent : undefined)

  useEffect(() => {
    if (!authed) return
    getHealth().then(setHealth).catch(() => {})
    getLogs(200).then((d) => setLines((prev) => {
      // Lines that arrived on the socket before the backlog came back are kept after it.
      const last = d.lines.length ? d.lines[d.lines.length - 1].seq : 0
      return [...d.lines, ...prev.filter((l) => l.seq > last)].slice(-MAX_LOG_LINES)
    })).catch(() => {})
  }, [authed])

  const logout = () => {
    setToken('')
    window.dispatchEvent(new CustomEvent('auth-changed'))
    setAuthed(false)
    setLines([])
    setHealth(null)
  }

  if (!authed) return <AuthGate onAuth={() => setAuthed(true)} />

  return (
    <div className="wrap">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
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

      <div className="dash">
        <div className="dash-col">
          <CameraFeed />
          <ScanSteps scan={scan} fading={fading} />
          <TodayPanel refreshKey={todayKey} />
        </div>
        <div className="dash-col dash-right">
          <HistoryTable refreshKey={todayKey} />
          <LiveFeed lines={lines} connected={connected} />
        </div>
      </div>
    </div>
  )
}
