import { useEffect, useState } from 'react'
import { getSessions, type AttendanceSession } from '../api'

const is: React.CSSProperties = {
  background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4,
  padding: '4px 8px', fontSize: 13,
}

export default function Sessions() {
  const [date, setDate] = useState('')
  const [studentId, setStudentId] = useState('')
  const [sessions, setSessions] = useState<AttendanceSession[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const fetch = () => {
    setLoading(true); setErr(null)
    getSessions({ date: date || undefined, student_id: studentId || undefined })
      .then(d => setSessions(d.sessions))
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [date, studentId])

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Sessions</h2>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} style={is} placeholder="Date" />
        <input value={studentId} onChange={e => setStudentId(e.target.value)} style={is} placeholder="Student ID" />
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      {sessions.length === 0 ? (
        <p style={{ opacity: 0.4, fontSize: 13 }}>No sessions found.</p>
      ) : (
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #333' }}>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Student</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Date</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Check-in</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Check-out</th>
              <th style={{ textAlign: 'right', padding: '6px 8px', opacity: 0.6 }}>Duration</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #1c1f27' }}>
                <td style={{ padding: '6px 8px' }}>{s.student_name || s.student_id}</td>
                <td style={{ padding: '6px 8px', opacity: 0.6 }}>{s.session_date}</td>
                <td style={{ padding: '6px 8px' }}>{new Date(s.check_in).toLocaleTimeString()}</td>
                <td style={{ padding: '6px 8px' }}>
                  {s.check_out ? new Date(s.check_out).toLocaleTimeString() : <span className="pill" style={{ background: '#1f5c2a' }}>in progress</span>}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                  {s.duration_minutes != null ? `${s.duration_minutes}m` : '\u2014'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
