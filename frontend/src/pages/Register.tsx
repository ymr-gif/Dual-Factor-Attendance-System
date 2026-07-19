import { useEffect, useRef, useState } from 'react'
import { getStudents, createStudent, enrollStudent, type Student, type EnrollResult } from '../api'

const is: React.CSSProperties = {
  background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4,
  padding: '4px 8px', fontSize: 13, minWidth: 120,
}

export default function Register() {
  const [students, setStudents] = useState<Student[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [creating, setCreating] = useState(false)
  const [cf, setCf] = useState({ student_id: '', uid: '', name: '', guardian_email: '' })
  const [shots, setShots] = useState<Blob[]>([])
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<EnrollResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const vr = useRef<HTMLVideoElement>(null)
  const cr = useRef<HTMLCanvasElement>(null)
  const sr = useRef<MediaStream | null>(null)

  useEffect(() => {
    getStudents().then(d => setStudents(d.students)).catch(e => setError(String(e)))
    navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      .then(s => { sr.current = s; if (vr.current) vr.current.srcObject = s })
      .catch(e => setError(`Camera: ${e.message}`))
    return () => { sr.current?.getTracks().forEach(t => t.stop()) }
  }, [])

  const capture = () => {
    const v = vr.current; const c = cr.current
    if (!v || !c) return
    c.width = v.videoWidth; c.height = v.videoHeight
    c.getContext('2d')!.drawImage(v, 0, 0)
    c.toBlob(b => { if (b) setShots(p => [...p, b]) }, 'image/jpeg', 0.9)
  }

  const createNew = async () => {
    try {
      const s = await createStudent({
        student_id: cf.student_id.trim().toUpperCase(), uid: cf.uid.trim().toUpperCase(),
        name: cf.name.trim() || undefined, guardian_email: cf.guardian_email.trim() || undefined,
      })
      setSelectedId(s.student_id); setCreating(false)
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

  return (
    <div className="page">
      <h2 style={{ margin: '0 0 16px', fontSize: 18 }}>Register Face</h2>
      {error && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', fontSize: 13, opacity: 0.6, marginBottom: 6 }}>Student</label>
        <select value={selectedId} onChange={e => { setSelectedId(e.target.value); setCreating(e.target.value === '__new__'); reset() }}
          style={{ width: '100%', background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4, padding: '6px 8px', fontSize: 13 }}>
          <option value="">\u2014 Select \u2014</option>
          <option value="__new__">+ Create new student...</option>
          {students.filter(s => !s.enrolled).map(s => (
            <option key={s.student_id} value={s.student_id}>{s.student_id} \u2014 {s.name || s.uid}</option>
          ))}
        </select>

        {creating && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            <input placeholder="Student ID *" value={cf.student_id} onChange={e => setCf(f => ({ ...f, student_id: e.target.value }))} style={is} />
            <input placeholder="UID *" value={cf.uid} onChange={e => setCf(f => ({ ...f, uid: e.target.value }))} style={is} />
            <input placeholder="Name" value={cf.name} onChange={e => setCf(f => ({ ...f, name: e.target.value }))} style={is} />
            <input placeholder="Guardian email" value={cf.guardian_email} onChange={e => setCf(f => ({ ...f, guardian_email: e.target.value }))} style={is} />
            <button className="btn btn-sm" onClick={createNew} disabled={!cf.student_id || !cf.uid}>Create</button>
          </div>
        )}
      </div>

      {selectedId && selectedId !== '__new__' && (
        <div className="card" style={{ marginBottom: 16 }}>
          <video ref={vr} autoPlay playsInline muted
            style={{ width: '100%', maxHeight: 320, borderRadius: 4, display: 'block', background: '#000' }} />
          <canvas ref={cr} style={{ display: 'none' }} />
          <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
            <button className="btn" onClick={capture} disabled={uploading}>Capture</button>
            <span style={{ fontSize: 12, opacity: 0.6 }}>{shots.length} frame(s)</span>
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
              {uploading ? 'Uploading...' : 'Enroll'}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="card">
          <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>Result</h3>
          <p style={{ fontSize: 13 }}>Frames used: {result.used} / {result.frames.length}</p>
          {result.duplicate && (
            <p style={{ fontSize: 13, color: '#d69e2e' }}>
              {'\u26A0'} Possible duplicate: {result.duplicate.name || result.duplicate.student_id} (sim: {result.duplicate.similarity.toFixed(3)})
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
