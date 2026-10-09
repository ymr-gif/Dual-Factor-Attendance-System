import { useEffect, useState } from 'react'
import { getSettings, setSetting } from '../api'
import CamerasPanel from '../components/CamerasPanel'
import SerialPortsPanel from '../components/SerialPortsPanel'

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [tunable, setTunable] = useState<string[]>([])
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const fetch = () => {
    setLoading(true); setErr(null)
    getSettings().then(d => {
      setSettings(d.settings); setTunable(d.tunable_keys)
      setEditing(p => { const n = { ...d.settings }; return Object.keys(n).length ? n : p })
    }).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [])

  const handleSave = async (key: string) => {
    setSaving(key)
    try {
      const r = await setSetting(key, editing[key] ?? '')
      setSettings(p => ({ ...p, [r.key]: r.value }))
    } catch (e) { setErr(String(e)) }
    setSaving(null)
  }

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Settings</h2>
        <button className="btn btn-sm btn-ghost" onClick={fetch}>Refresh</button>
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      {tunable.length === 0 ? (
        <p style={{ opacity: 0.4 }}>No tunable settings.</p>
      ) : (
        <div className="card">
          {tunable.map(key => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #1c1f27' }}>
              <code style={{ minWidth: 200, fontSize: 12 }}>{key}</code>
              <input value={editing[key] ?? ''} onChange={e => setEditing(p => ({ ...p, [key]: e.target.value }))}
                style={{ flex: 1, background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4, padding: '4px 8px', fontSize: 13 }} />
              <button className="btn btn-sm" onClick={() => handleSave(key)} disabled={saving === key}>
                {saving === key ? '...' : 'Save'}
              </button>
            </div>
          ))}
        </div>
      )}

      <SerialPortsPanel />
      <CamerasPanel />

      {Object.keys(settings).length > 0 && (
        <details style={{ marginTop: 24, opacity: 0.5 }}>
          <summary style={{ fontSize: 13, cursor: 'pointer' }}>All ({Object.keys(settings).length})</summary>
          <pre style={{ fontSize: 11, marginTop: 8, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(settings, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
