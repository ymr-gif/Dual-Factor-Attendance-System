import { useEffect, useState } from 'react'
import { getAudit, type AuditEntry } from '../api'

const ACTION_COLORS: Record<string, string> = {
  enroll: '#1f5c2a',
  consent: '#5c4a1f',
  erase: '#5c1f22',
  review_resolve: '#333',
}

export default function Audit() {
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [limit, setLimit] = useState(100)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const fetch = () => {
    setLoading(true); setErr(null)
    getAudit(limit).then(d => setAudit(d.audit)).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [limit])

  if (loading) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Audit Log</h2>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          style={{ background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4, padding: '4px 8px', fontSize: 13 }}>
          <option value={100}>100</option>
          <option value={500}>500</option>
          <option value={1000}>1000</option>
        </select>
        <button className="btn btn-sm btn-ghost" onClick={fetch}>Refresh</button>
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err}</p>}

      {audit.length === 0 ? (
        <p style={{ opacity: 0.4, fontSize: 13 }}>No audit entries.</p>
      ) : (
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #333' }}>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Time</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Actor</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Action</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Target</th>
              <th style={{ textAlign: 'left', padding: '6px 8px', opacity: 0.6 }}>Detail</th>
            </tr>
          </thead>
          <tbody>
            {audit.map(e => (
              <tr key={e.id} style={{ borderBottom: '1px solid #1c1f27' }}>
                <td style={{ padding: '6px 8px', opacity: 0.6, whiteSpace: 'nowrap' }}>{new Date(e.ts).toLocaleString()}</td>
                <td style={{ padding: '6px 8px' }}>{e.actor || '\u2014'}</td>
                <td style={{ padding: '6px 8px' }}>
                  <span className="pill" style={{ background: ACTION_COLORS[e.action] || '#333' }}>{e.action}</span>
                </td>
                <td style={{ padding: '6px 8px' }}>{e.target || '\u2014'}</td>
                <td style={{ padding: '6px 8px', opacity: 0.6, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.detail || '\u2014'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
