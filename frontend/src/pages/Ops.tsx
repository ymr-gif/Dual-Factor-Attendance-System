import { useEffect, useState } from 'react'
import { getHealth, getStatsToday, getConfig, reqText, type Health, type StatsToday, type Config } from '../api'

export default function Ops() {
  const [health, setHealth] = useState<Health | null>(null)
  const [stats, setStats] = useState<StatsToday | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [metrics, setMetrics] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const fetch = () => {
    setLoading(true); setErr(null)
    Promise.all([
      getHealth().catch(() => null),
      getStatsToday().catch(() => null),
      getConfig().catch(() => null),
      reqText('/metrics').catch(() => null),
    ]).then(([h, s, c, m]) => {
      setHealth(h); setStats(s); setConfig(c); setMetrics(m)
    }).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [])
  useEffect(() => { const id = setInterval(fetch, 10000); return () => clearInterval(id) }, [])

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Ops / Health</h2>
        <button className="btn btn-sm btn-ghost" onClick={fetch}>Refresh</button>
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <div className="card" style={{ flex: 1, minWidth: 140 }}>
          <div style={{ fontSize: 13, opacity: 0.6, marginBottom: 4 }}>Database</div>
          <span className="pill" style={{ background: health?.db ? '#1f5c2a' : '#5c1f22', fontSize: 13 }}>
            {health?.db ? 'Connected' : 'Down'}
          </span>
        </div>
        <div className="card" style={{ flex: 1, minWidth: 140, textAlign: 'center' }}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{stats?.total ?? 0}</div>
          <div style={{ fontSize: 13, opacity: 0.6 }}>Taps today</div>
        </div>
        {stats && Object.entries(stats.by_status).map(([k, v]) => (
          <div key={k} className="card" style={{ flex: 1, minWidth: 100, textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div>
            <div style={{ fontSize: 12, opacity: 0.6 }}>{k}</div>
          </div>
        ))}
      </div>

      {config && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>Config</h3>
          <pre style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: 0, opacity: 0.7 }}>
            {JSON.stringify(config, null, 2)}
          </pre>
        </div>
      )}

      {metrics && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ fontSize: 13, cursor: 'pointer', opacity: 0.6 }}>Prometheus Metrics</summary>
          <pre style={{ fontSize: 11, marginTop: 8, whiteSpace: 'pre-wrap', opacity: 0.7 }}>{metrics}</pre>
        </details>
      )}
    </div>
  )
}
