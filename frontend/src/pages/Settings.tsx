import { useEffect, useState } from 'react'
import { getConfig, getSettings, setSetting } from '../api'
import CalibrationPanel from '../components/CalibrationPanel'
import CamerasPanel from '../components/CamerasPanel'
import SerialPortsPanel from '../components/SerialPortsPanel'

// Preset choices for the tunable-settings boxes below, so pilot day is picking from a
// list instead of typing a raw value under pressure. Any tunable key without a preset
// here still falls back to a free-text box.
const PRESETS: Record<string, { value: string; label: string }[]> = {
  enforce_2fa: [
    { value: 'false', label: 'false — failed 2nd factor still counts (flagged)' },
    { value: 'true', label: 'true — failed 2nd factor is rejected, does not count' },
  ],
  liveness_threshold: [
    { value: '', label: '(unset) — the model\'s own argmax verdict' },
    { value: '0.3', label: '0.3' },
    { value: '0.35', label: '0.35 — deduced from the 2026-11-18 session log' },
    { value: '0.4', label: '0.4' },
    { value: '0.5', label: '0.5' },
    { value: '0.6', label: '0.6' },
  ],
}

function presetOptions(key: string, current: string) {
  const base = PRESETS[key] ?? []
  if (base.some(o => o.value === current)) return base
  // The saved value doesn't match a preset (e.g. a custom number set earlier) --
  // show it anyway rather than silently swap it for the first option.
  return [{ value: current, label: `${current || '(empty)'} — current` }, ...base]
}

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [tunable, setTunable] = useState<string[]>([])
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  // The two-factor switch as the tap path sees it (saved value, else ENFORCE_2FA).
  const [enforce, setEnforce] = useState<boolean | null>(null)
  const [perceptionOn, setPerceptionOn] = useState(false)

  const fetch = () => {
    setLoading(true); setErr(null)
    getSettings().then(d => {
      setSettings(d.settings); setTunable(d.tunable_keys)
      setEditing(p => { const n = { ...d.settings }; return Object.keys(n).length ? n : p })
    }).catch(e => setErr(String(e))).finally(() => setLoading(false))
    getConfig().then(c => { setEnforce(c.decision.enforce_2fa); setPerceptionOn(c.perception.enabled) })
      .catch(e => setErr(String(e)))
  }

  const toggleEnforce = async () => {
    if (enforce === null) return
    setSaving('enforce_2fa')
    try {
      await setSetting('enforce_2fa', enforce ? 'false' : 'true')
      const c = await getConfig()
      setEnforce(c.decision.enforce_2fa)
      fetch()
    } catch (e) { setErr(String(e)) }
    setSaving(null)
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

      <div className="card" style={{ marginBottom: 16 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
          <input type="checkbox" checked={enforce === true} disabled={enforce === null || saving === 'enforce_2fa'}
            onChange={toggleEnforce} />
          <strong style={{ fontSize: 14 }}>Two-factor enforcement</strong>
          <span style={{ fontSize: 12, opacity: 0.6 }}>{enforce === null ? '' : enforce ? 'ON' : 'OFF'}</span>
        </label>
        <p style={{ fontSize: 12, opacity: 0.6, margin: '8px 0 0' }}>
          OFF: a tap whose face or liveness check fails is logged <code>flagged</code> and still counts.
          ON: it is logged <code>rejected</code> and does not count. Takes effect on the next tap; every change is in the audit log.
          {perceptionOn && ' The camera pipeline is on: a wrong face or a spoof never counts either way, so this switch only matters with the pipeline off.'}
        </p>
      </div>

      <CalibrationPanel />

      {tunable.length === 0 ? (
        <p style={{ opacity: 0.4 }}>No tunable settings.</p>
      ) : (
        <div className="card">
          {tunable.map(key => {
            const value = editing[key] ?? ''
            const options = PRESETS[key] ? presetOptions(key, value) : null
            const fieldStyle = { flex: 1, background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4, padding: '4px 8px', fontSize: 13 }
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #1c1f27' }}>
                <code style={{ minWidth: 200, fontSize: 12 }}>{key}</code>
                {options ? (
                  <select value={value} onChange={e => setEditing(p => ({ ...p, [key]: e.target.value }))} style={fieldStyle}>
                    {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : (
                  <input value={value} onChange={e => setEditing(p => ({ ...p, [key]: e.target.value }))} style={fieldStyle} />
                )}
                <button className="btn btn-sm" onClick={() => handleSave(key)} disabled={saving === key}>
                  {saving === key ? '...' : 'Save'}
                </button>
              </div>
            )
          })}
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
