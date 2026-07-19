import { useEffect, useRef, useState } from 'react'
import {
  getStudents, createStudent, enrollStudent, getPerceptionState,
  type Student, type EnrollResult, type PerceptionState,
} from '../api'
import { useTapStream } from '../useTapStream'

const is: React.CSSProperties = {
  background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4,
  padding: '4px 8px', fontSize: 13, minWidth: 120,
}

type CamSource = 'user' | 'stream' | 'none'

export default function Register() {
  const [students, setStudents] = useState<Student[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [creating, setCreating] = useState(false)
  const [cf, setCf] = useState({ student_id: '', uid: '', name: '', guardian_email: '' })
  const [shots, setShots] = useState<Blob[]>([])
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<EnrollResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [camSource, setCamSource] = useState<CamSource>('none')
  const [camNote, setCamNote] = useState<string | null>(null)
  const [pstate, setPstate] = useState<PerceptionState | null>(null)
  const [scanningUid, setScanningUid] = useState(false)
  const vr = useRef<HTMLVideoElement>(null)
  const ir = useRef<HTMLImageElement>(null)
  const cr = useRef<HTMLCanvasElement>(null)
  const sr = useRef<MediaStream | null>(null)
  const scanTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    getStudents().then(d => setStudents(d.students)).catch(e => setError(String(e)))
    // Prefer the local webcam. If it's busy — the backend perception service is the
    // single camera owner and holds /dev/video0 — fall back to the server MJPEG stream.
    navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      .then(s => { sr.current = s; setCamSource('user'); if (vr.current) vr.current.srcObject = s })
      .catch(() => {
        setCamSource('stream')
        setCamNote('Local camera unavailable (backend perception owns it) — capturing from the server stream. Frames include detection boxes.')
      })
    return () => { sr.current?.getTracks().forEach(t => t.stop()) }
  }, [])

  // Re-attach the stream if the <video> mounts after getUserMedia resolved.
  useEffect(() => {
    if (camSource === 'user' && vr.current && sr.current) vr.current.srcObject = sr.current
  }, [camSource, selectedId, creating])

  // Poll the live camera-quality gate (perception's own detections — one person,
  // lighting, distance, framing). Drives the guidance + the capture button.
  useEffect(() => {
    let alive = true
    const tick = () => getPerceptionState().then(s => { if (alive) setPstate(s) }).catch(() => {})
    tick()
    const id = setInterval(tick, 700)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // Scan-to-fill UID: while armed, the next tapped card fills the UID field.
  useTapStream(e => {
    if (!scanningUid) return
    const uid = e.log?.uid
    if (!uid) return
    setCf(f => ({ ...f, uid }))
    stopScan()
  })

  const stopScan = () => {
    if (scanTimer.current) { clearTimeout(scanTimer.current); scanTimer.current = null }
    setScanningUid(false)
  }
  const startScan = () => {
    setError(null)
    setScanningUid(true)
    scanTimer.current = setTimeout(() => { setScanningUid(false); scanTimer.current = null }, 20000)
  }

  // Gate: block capture only when perception is actively saying "not ready".
  // In getUserMedia mode (perception off) the gate is soft — never blocks.
  const gateActive = pstate?.enabled === true
  const gateBlocked = gateActive && pstate?.ready === false

  const capture = () => {
    const c = cr.current
    if (!c) return
    let src: CanvasImageSource | null = null
    let w = 0, h = 0
    if (camSource === 'user' && vr.current) { src = vr.current; w = vr.current.videoWidth; h = vr.current.videoHeight }
    else if (camSource === 'stream' && ir.current) { src = ir.current; w = ir.current.naturalWidth; h = ir.current.naturalHeight }
    if (!src || !w || !h) { setError('No camera frame yet — is the camera connected?'); return }
    c.width = w; c.height = h
    c.getContext('2d')!.drawImage(src, 0, 0, w, h)
    c.toBlob(b => { if (b) setShots(p => [...p, b]) }, 'image/jpeg', 0.9)
  }

  const createNew = async () => {
    try {
      const s = await createStudent({
        student_id: cf.student_id.trim().toUpperCase(), uid: cf.uid.trim().toUpperCase(),
        name: cf.name.trim() || undefined, guardian_email: cf.guardian_email.trim() || undefined,
      })
      setSelectedId(s.student_id); setCreating(false); stopScan()
      setStudents(p => [...p, s])
    } catch (e) { setError(String(e)) }
  }

  const handleEnroll = async () => {
    if (!selectedId || shots.length === 0) return
    setUploading(true); setError(null); setResult(null)
    const fd = new FormData()
    shots.forEach((b, i) => fd.append('images', b, `frame_${i}.jpg`))
    try { setResult(await enrollStudent(selectedId, fd)) }
    catch (e) { setError(String(e)) }
    setUploading(false)
  }

  const reset = () => { setShots([]); setResult(null); setError(null); setUploading(false) }

  const enrolling = selectedId && selectedId !== '__new__'
  const showCamera = creating || enrolling

  return (
    <div className="page">
      <h2 style={{ margin: '0 0 16px', fontSize: 18 }}>Register Face</h2>
      {error && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', fontSize: 13, opacity: 0.6, marginBottom: 6 }}>Student</label>
        <select value={selectedId} onChange={e => { setSelectedId(e.target.value); setCreating(e.target.value === '__new__'); reset(); stopScan() }}
          style={{ width: '100%', background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4, padding: '6px 8px', fontSize: 13 }}>
          <option value="">— Select —</option>
          <option value="__new__">+ Create new student…</option>
          {students.filter(s => !s.enrolled).map(s => (
            <option key={s.student_id} value={s.student_id}>{s.student_id} — {s.name || s.uid}</option>
          ))}
        </select>

        {creating && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8, alignItems: 'center' }}>
            <input placeholder="Student ID *" value={cf.student_id} onChange={e => setCf(f => ({ ...f, student_id: e.target.value }))} style={is} />
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <input placeholder="UID *" value={cf.uid} onChange={e => setCf(f => ({ ...f, uid: e.target.value }))} style={is} />
              <button className="btn btn-sm btn-ghost" type="button"
                onClick={scanningUid ? stopScan : startScan}
                title="Tap a blank NFC card on the reader to fill this automatically">
                {scanningUid ? 'Waiting… cancel' : 'Scan UID'}
              </button>
            </div>
            <input placeholder="Name" value={cf.name} onChange={e => setCf(f => ({ ...f, name: e.target.value }))} style={is} />
            <input placeholder="Guardian email" value={cf.guardian_email} onChange={e => setCf(f => ({ ...f, guardian_email: e.target.value }))} style={is} />
            <button className="btn btn-sm" onClick={createNew} disabled={!cf.student_id || !cf.uid}>Create</button>
          </div>
        )}
        {creating && scanningUid && (
          <p style={{ fontSize: 12, color: '#6ea8fe', margin: '8px 0 0' }}>Tap a card on the reader now… (auto-cancels in 20s)</p>
        )}
      </div>

      {showCamera && (
        <div className="card" style={{ marginBottom: 16 }}>
          {camNote && <p style={{ fontSize: 12, color: '#d69e2e', margin: '0 0 8px' }}>{'⚠'} {camNote}</p>}

          <div style={{ maxWidth: 420 }}>
            {camSource === 'stream'
              ? <img ref={ir} src="/stream.mjpeg" alt="camera"
                  onError={() => setCamNote('Server camera stream offline — no frames available.')}
                  style={{ width: '100%', maxHeight: 320, objectFit: 'contain', borderRadius: 4, display: 'block', background: '#000' }} />
              : <video ref={vr} autoPlay playsInline muted
                  style={{ width: '100%', maxHeight: 320, borderRadius: 4, display: 'block', background: '#000' }} />}
          </div>
          <canvas ref={cr} style={{ display: 'none' }} />

          {/* Live quality gate */}
          <div style={{ marginTop: 8 }}>
            {gateActive ? (
              <span className="pill" style={{ background: pstate?.ready ? '#1f5c2a' : '#5c4a1f' }}>
                {pstate?.ready ? '✓ ' : '● '}{pstate?.reason}
              </span>
            ) : (
              <span style={{ fontSize: 12, opacity: 0.6 }}>Live quality check unavailable (perception off) — capture allowed.</span>
            )}
          </div>

          {enrolling && (
            <>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
                <button className="btn" onClick={capture} disabled={uploading || gateBlocked}
                  title={gateBlocked ? pstate?.reason : 'Capture a frame'}>Capture</button>
                <span style={{ fontSize: 12, opacity: 0.6 }}>{shots.length} frame(s) · aim for 3–5</span>
              </div>
              {shots.length > 0 && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8, alignItems: 'center' }}>
                  {shots.map((b, i) => (
                    <img key={i} src={URL.createObjectURL(b)}
                      style={{ width: 80, height: 60, objectFit: 'cover', borderRadius: 4 }} alt={`frame ${i}`} />
                  ))}
                  <button className="btn btn-sm btn-ghost" onClick={() => setShots([])} disabled={uploading}>Clear</button>
                </div>
              )}
              <div style={{ marginTop: 12 }}>
                <button className="btn" onClick={handleEnroll} disabled={uploading || shots.length === 0}>
                  {uploading ? 'Uploading…' : 'Enroll'}
                </button>
              </div>
            </>
          )}
          {creating && (
            <p style={{ fontSize: 12, opacity: 0.6, marginTop: 8 }}>Fill in the student and press Create to start capturing.</p>
          )}
        </div>
      )}

      {result && (
        <div className="card">
          <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>Result</h3>
          <p style={{ fontSize: 13 }}>Frames used: {result.used} / {result.frames.length}</p>
          {result.duplicate && (
            <p style={{ fontSize: 13, color: '#d69e2e' }}>
              {'⚠'} Possible duplicate: {result.duplicate.name || result.duplicate.student_id} (sim: {result.duplicate.similarity.toFixed(3)})
            </p>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            {result.frames.map((f, i) => (
              <span key={i} className="pill" style={{ background: f.status === 'accepted' ? '#1f5c2a' : '#5c1f22' }}>
                {f.file}: {f.status}{f.reason ? ` (${f.reason})` : ''}
              </span>
            ))}
          </div>
          <button className="btn btn-sm btn-ghost" style={{ marginTop: 12 }} onClick={reset}>Enroll another</button>
        </div>
      )}
    </div>
  )
}
