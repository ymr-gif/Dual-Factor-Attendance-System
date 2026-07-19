import { useEffect, useState } from 'react'
import { getReviewQueue, resolveReview, type ReviewQueueItem } from '../api'

const C: Record<string, string> = {
  accepted: '#1f5c2a', flagged: '#5c4a1f', rejected: '#5c1f22',
  spoof: '#5c1f22', mismatch: '#5c1f22', no_face: '#5c4a1f',
  tailgating: '#5c1f22', unverified: '#333', unregistered: '#333',
}

export default function Review() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const fetch = () => {
    setLoading(true); setErr(null)
    getReviewQueue().then(d => setQueue(d.queue)).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [])

  const handleResolve = async (id: number, resolution: string) => {
    if (!confirm(`Resolve as "${resolution}"?`)) return
    try { await resolveReview(id, resolution); setQueue(p => p.filter(r => r.id !== id)) }
    catch (e) { setErr(String(e)) }
  }

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Review Queue</h2>
        <button className="btn btn-sm btn-ghost" onClick={fetch}>Refresh</button>
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      {queue.length === 0 ? (
        <p style={{ opacity: 0.4 }}>No pending reviews.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #333', textAlign: 'left' }}>
                <th style={{ padding: '6px 8px' }}>Time</th>
                <th style={{ padding: '6px 8px' }}>Student</th>
                <th style={{ padding: '6px 8px' }}>UID</th>
                <th style={{ padding: '6px 8px' }}>Status</th>
                <th style={{ padding: '6px 8px' }}>Reason</th>
                <th style={{ padding: '6px 8px' }}>Face</th>
                <th style={{ padding: '6px 8px' }}>Live</th>
                <th style={{ padding: '6px 8px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {queue.map(r => (
                <tr key={r.id} style={{ borderBottom: '1px solid #1c1f27' }}>
                  <td style={{ padding: '6px 8px', whiteSpace: 'nowrap', fontSize: 12 }}>
                    {r.log_ts ? new Date(r.log_ts).toLocaleTimeString() : '\u2014'}
                  </td>
                  <td style={{ padding: '6px 8px' }}>{r.student_name || r.student_id || '\u2014'}</td>
                  <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 12 }}>{r.uid || '\u2014'}</td>
                  <td style={{ padding: '6px 8px' }}>
                    <span className="pill" style={{ background: C[r.status] || '#333' }}>{r.status}</span>
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 12, opacity: 0.7 }}>{r.reason || '\u2014'}</td>
                  <td style={{ padding: '6px 8px', fontSize: 12 }}>
                    {r.face_score != null ? `${r.face_score.toFixed(2)} ${r.face_match ? '\u2713' : '\u2717'}` : '\u2014'}
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 12 }}>
                    {r.liveness_score != null ? `${r.liveness_score.toFixed(2)} ${r.liveness_pass ? '\u2713' : '\u2717'}` : '\u2014'}
                  </td>
                  <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                    <button className="btn btn-sm" style={{ background: '#1f5c2a', marginRight: 4 }}
                      onClick={() => handleResolve(r.id, 'confirmed')}>Confirm</button>
                    <button className="btn btn-sm" style={{ background: '#5c4a1f', marginRight: 4 }}
                      onClick={() => handleResolve(r.id, 'override')}>Override</button>
                    <button className="btn btn-sm btn-ghost"
                      onClick={() => handleResolve(r.id, 'dismiss')}>Dismiss</button>
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
