import { useEffect, useState } from 'react'
import { getSummary, downloadAttendanceCsv, type AttendanceSummary } from '../api'

const is: React.CSSProperties = {
  background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4,
  padding: '4px 8px', fontSize: 13,
}

export default function Summary() {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [data, setData] = useState<AttendanceSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const fetch = () => {
    setLoading(true); setErr(null)
    getSummary(date || undefined).then(setData).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [date])

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Attendance Summary</h2>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} style={is} />
        <button className="btn btn-sm" onClick={() => downloadAttendanceCsv({ date })}>Download CSV</button>
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
            <div className="card" style={{ flex: 1, minWidth: 140, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{data.present.length}/{data.expected}</div>
              <div style={{ fontSize: 13, opacity: 0.6 }}>Present</div>
            </div>
            <div className="card" style={{ flex: 1, minWidth: 140, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: data.late_count > 0 ? '#d69e2e' : undefined }}>{data.late_count}</div>
              <div style={{ fontSize: 13, opacity: 0.6 }}>Late{data.late_cutoff ? ` (after ${data.late_cutoff})` : ''}</div>
            </div>
            <div className="card" style={{ flex: 1, minWidth: 140, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: data.absent.length > 0 ? '#e53e3e' : undefined }}>{data.absent.length}</div>
              <div style={{ fontSize: 13, opacity: 0.6 }}>Absent</div>
            </div>
          </div>

          <h3 style={{ fontSize: 14, margin: '0 0 8px' }}>Present ({data.present.length})</h3>
          {data.present.length === 0 ? (
            <p style={{ opacity: 0.4, fontSize: 13 }}>No students present.</p>
          ) : (
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #333' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Student</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>ID</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.present.map(p => (
                  <tr key={p.student_id} style={{ borderBottom: '1px solid #1c1f27' }}>
                    <td style={{ padding: '6px 8px' }}>{p.name || '\u2014'}</td>
                    <td style={{ padding: '6px 8px', opacity: 0.6 }}>{p.student_id}</td>
                    <td style={{ padding: '6px 8px' }}>
                      {p.late && <span className="pill" style={{ background: '#5c4a1f' }}>late</span>}
                      {!p.late && <span className="pill" style={{ background: '#1f5c2a' }}>on time</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3 style={{ fontSize: 14, margin: '24px 0 8px' }}>Absent ({data.absent.length})</h3>
          {data.absent.length === 0 ? (
            <p style={{ opacity: 0.4, fontSize: 13 }}>All students present.</p>
          ) : (
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #333' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Student</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>ID</th>
                </tr>
              </thead>
              <tbody>
                {data.absent.map(a => (
                  <tr key={a.student_id} style={{ borderBottom: '1px solid #1c1f27' }}>
                    <td style={{ padding: '6px 8px' }}>{a.name || '\u2014'}</td>
                    <td style={{ padding: '6px 8px', opacity: 0.6 }}>{a.student_id}</td>
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
