// First-run wizard (Step 42) — non-technical setup entirely in the browser:
// set operator token -> check DB/camera/reader -> enroll first student.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSetupStatus, getPerceptionState, setToken, getToken, type SetupStatus, type PerceptionState } from '../api'

function Check({ ok, label, hint }: { ok: boolean | null; label: string; hint?: string }) {
  const color = ok == null ? '#5c4a1f' : ok ? '#1f5c2a' : '#5c1f22'
  const mark = ok == null ? '…' : ok ? '✓' : '✗'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0' }}>
      <span className="pill" style={{ background: color, minWidth: 26, textAlign: 'center' }}>{mark}</span>
      <div>
        <div style={{ fontSize: 14 }}>{label}</div>
        {hint && <div style={{ fontSize: 12, opacity: 0.6 }}>{hint}</div>}
      </div>
    </div>
  )
}

export default function SetupWizard() {
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [pstate, setPstate] = useState<PerceptionState | null>(null)
  const [tokenInput, setTokenInput] = useState(getToken())
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let alive = true
    const tick = () => {
      getSetupStatus().then(s => alive && setStatus(s)).catch(() => alive && setStatus(null))
      getPerceptionState().then(s => alive && setPstate(s)).catch(() => {})
    }
    tick()
    const id = setInterval(tick, 1500)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const saveToken = () => {
    setToken(tokenInput.trim())
    window.dispatchEvent(new CustomEvent('auth-changed'))
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  const camReady = pstate?.enabled ? !!pstate?.ready || pstate?.reason?.startsWith('No face') : null

  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 20 }}>First-run setup</h2>
      <p style={{ fontSize: 13, opacity: 0.6, marginTop: 0 }}>
        Get the guardpost running in three steps. No terminal needed.
      </p>

      {/* Step 1 — token */}
      <div className="card">
        <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>1 · Operator access</h3>
        <p style={{ fontSize: 13, opacity: 0.7, marginTop: 0 }}>
          {status?.token_required
            ? 'The backend requires an operator token. Paste it here to manage the roster and settings.'
            : 'The backend is in open mode (no token set). You can add one later on the server for access control.'}
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="password" placeholder="Operator token (optional in open mode)"
            value={tokenInput} onChange={e => setTokenInput(e.target.value)}
            style={{ flex: 1, background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4, padding: '6px 10px', fontSize: 13 }}
          />
          <button className="btn" onClick={saveToken}>{saved ? 'Saved ✓' : 'Save'}</button>
        </div>
      </div>

      {/* Step 2 — system checks */}
      <div className="card">
        <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>2 · System checks</h3>
        <Check ok={status ? status.db : null} label="Database" hint="Postgres reachable, schema applied" />
        <Check
          ok={status ? status.perception.enabled : null}
          label="Camera / perception service"
          hint={status?.perception.enabled
            ? (status.perception.camera_fresh ? 'Live frames arriving' : 'Enabled — waiting for frames')
            : 'Perception disabled (PERCEPTION_ENABLED=false)'}
        />
        <Check ok={camReady} label="Camera quality gate" hint={pstate?.reason ?? 'Waiting…'} />
        <p style={{ fontSize: 12, opacity: 0.55, margin: '8px 0 0' }}>
          NFC reader runs as its own service — tap a card and watch the live feed on the Dashboard to confirm it.
        </p>
      </div>

      {/* Step 3 — first student */}
      <div className="card">
        <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>3 · Enroll the first student</h3>
        <p style={{ fontSize: 13, opacity: 0.7, marginTop: 0 }}>
          Roster: {status?.students.total ?? '—'} students, {status?.students.enrolled ?? '—'} with a face enrolled.
        </p>
        <Link to="/register" className="btn" style={{ textDecoration: 'none', display: 'inline-block' }}>
          Open the register wizard →
        </Link>
      </div>

      {/* Done */}
      <div className="card" style={{ background: status?.ready ? '#16351d' : '#1c1f27' }}>
        <h3 style={{ margin: '0 0 6px', fontSize: 15 }}>
          {status?.ready ? '✓ Ready to run' : 'Almost there'}
        </h3>
        <p style={{ fontSize: 13, opacity: 0.75, margin: 0 }}>
          {status?.ready
            ? 'Database is up and at least one student is enrolled. Open the Dashboard to watch live taps, or the Kiosk for the verdict screen.'
            : 'Finish the checks above (DB up + one enrolled student) to go live.'}
        </p>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <Link to="/" className="btn btn-ghost" style={{ textDecoration: 'none' }}>Dashboard</Link>
          <Link to="/kiosk" className="btn btn-ghost" style={{ textDecoration: 'none' }}>Kiosk</Link>
          <Link to="/viewer" className="btn btn-ghost" style={{ textDecoration: 'none' }}>Viewer</Link>
        </div>
      </div>
    </div>
  )
}
