import { useEffect, useRef, useState } from 'react'
import { searchFace, type FaceMatch } from '../api'

export default function Lookup() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [matches, setMatches] = useState<FaceMatch[]>([])
  const [searching, setSearching] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fr = useRef<HTMLInputElement>(null)
  const vr = useRef<HTMLVideoElement>(null)
  const cr = useRef<HTMLCanvasElement>(null)
  const sr = useRef<MediaStream | null>(null)
  const [camActive, setCamActive] = useState(false)

  useEffect(() => () => { sr.current?.getTracks().forEach(t => t.stop()) }, [])

  const startCam = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      sr.current = s; if (vr.current) vr.current.srcObject = s; setCamActive(true)
    } catch (e) { setErr(`Camera: ${e instanceof Error ? e.message : String(e)}`) }
  }

  const stopCam = () => { sr.current?.getTracks().forEach(t => t.stop()); sr.current = null; setCamActive(false) }

  const captureFromCam = () => {
    const v = vr.current; const c = cr.current
    if (!v || !c) return
    c.width = v.videoWidth; c.height = v.videoHeight
    c.getContext('2d')!.drawImage(v, 0, 0)
    c.toBlob(b => {
      if (b) {
        const f = new File([b], 'capture.jpg', { type: 'image/jpeg' })
        setFile(f); setPreview(URL.createObjectURL(b)); stopCam()
      }
    }, 'image/jpeg', 0.9)
  }

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) { setFile(f); setPreview(URL.createObjectURL(f)); setMatches([]); setErr(null) }
  }

  const doSearch = async () => {
    if (!file) return
    setSearching(true); setErr(null); setMatches([])
    try { const r = await searchFace(file); setMatches(r.matches) }
    catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('422')) setErr('No usable face detected in image.')
      else if (msg.includes('400')) setErr('Could not decode image.')
      else setErr(msg)
    }
    setSearching(false)
  }

  return (
    <div className="page">
      <h2 style={{ margin: '0 0 16px', fontSize: 18 }}>Face Lookup</h2>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <input ref={fr} type="file" accept="image/*" onChange={onFileChange} style={{ fontSize: 13 }} />
          {!camActive && <button className="btn btn-sm btn-ghost" onClick={startCam}>Use Camera</button>}
          {camActive && <button className="btn btn-sm btn-ghost" onClick={stopCam}>Cancel Camera</button>}
        </div>

        {camActive && (
          <div style={{ marginBottom: 12 }}>
            <video ref={vr} autoPlay playsInline muted
              style={{ width: '100%', maxHeight: 320, borderRadius: 4, display: 'block', background: '#000' }} />
            <canvas ref={cr} style={{ display: 'none' }} />
            <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={captureFromCam}>Capture</button>
          </div>
        )}

        {preview && (
          <div style={{ marginBottom: 12 }}>
            <img src={preview} style={{ maxWidth: 320, maxHeight: 240, borderRadius: 4, display: 'block' }} alt="Upload preview" />
          </div>
        )}

        <button className="btn" onClick={doSearch} disabled={!file || searching}>
          {searching ? 'Searching...' : 'Search'}
        </button>
      </div>

      {matches.length > 0 && (
        <div className="card">
          <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>Results ({matches.length})</h3>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #333' }}>
                <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>#</th>
                <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Student</th>
                <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>UID</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', opacity: 0.6 }}>Similarity</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m, i) => (
                <tr key={m.student_id} style={{ borderBottom: '1px solid #1c1f27' }}>
                  <td style={{ padding: '6px 8px', opacity: 0.4 }}>{i + 1}</td>
                  <td style={{ padding: '6px 8px' }}>{m.name || m.student_id}</td>
                  <td style={{ padding: '6px 8px', opacity: 0.6 }}>{m.uid}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                    <span className="pill" style={{ background: m.similarity >= 0.6 ? '#1f5c2a' : '#5c4a1f' }}>
                      {(m.similarity * 100).toFixed(1)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
