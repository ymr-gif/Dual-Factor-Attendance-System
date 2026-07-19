import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getReenrollDue, type ReenrollDue } from '../api'

export default function Reenroll() {
  const [data, setData] = useState<ReenrollDue | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    getReenrollDue().then(setData).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <h2 style={{ margin: '0 0 16px', fontSize: 18 }}>Re-enrollment Due</h2>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      {data && (
        <>
          <div className="card" style={{ marginBottom: 16, fontSize: 13 }}>
            <span style={{ opacity: 0.6 }}>Current model: </span><code>{data.current_model}</code>
            <span style={{ opacity: 0.6, marginLeft: 16 }}>Re-enroll after: </span><code>{data.reenroll_after_days} days</code>
          </div>

          {data.due.length === 0 ? (
            <p style={{ opacity: 0.4, fontSize: 13 }}>No students due for re-enrollment.</p>
          ) : (
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #333' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Student</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Embed Model</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Enrolled At</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}></th>
                </tr>
              </thead>
              <tbody>
                {data.due.map(d => (
                  <tr key={d.student_id} style={{ borderBottom: '1px solid #1c1f27' }}>
                    <td style={{ padding: '6px 8px' }}>{d.name || d.student_id}</td>
                    <td style={{ padding: '6px 8px' }}>
                      <code>{d.embed_model || 'unknown (pre-provenance)'}</code>
                    </td>
                    <td style={{ padding: '6px 8px', opacity: 0.6 }}>{d.enrolled_at ? new Date(d.enrolled_at).toLocaleDateString() : '\u2014'}</td>
                    <td style={{ padding: '6px 8px' }}>
                      <Link to="/register" style={{ fontSize: 12 }}>Re-enroll</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
