import { useEffect, useState } from 'react'
import { getStudents, createStudent, updateStudent, deleteStudent, setConsent, type Student } from '../api'

interface FormState { student_id: string; uid: string; name: string; guardian_email: string }
const empty = (): FormState => ({ student_id: '', uid: '', name: '', guardian_email: '' })

const is: React.CSSProperties = {
  background: '#12141a', color: '#e6e8ee', border: '1px solid #333', borderRadius: 4,
  padding: '4px 8px', fontSize: 13, minWidth: 100,
}

export default function Roster() {
  const [students, setStudents] = useState<Student[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [add, setAdd] = useState<FormState>(empty)
  const [editId, setEditId] = useState<string | null>(null)
  const [edit, setEdit] = useState({ uid: '', name: '', guardian_email: '' })

  const fetch = () => {
    setLoading(true); setErr(null)
    getStudents().then(d => setStudents(d.students)).catch(e => setErr(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [])

  const handleAdd = async () => {
    try {
      await createStudent({ student_id: add.student_id.trim().toUpperCase(), uid: add.uid.trim().toUpperCase(), name: add.name.trim() || undefined, guardian_email: add.guardian_email.trim() || undefined })
      setShowAdd(false); setAdd(empty()); fetch()
    } catch (e) { setErr(String(e)) }
  }

  const startEdit = (s: Student) => {
    setEditId(s.student_id); setEdit({ uid: s.uid, name: s.name || '', guardian_email: s.guardian_email || '' })
  }

  const handleUpdate = async (id: string) => {
    try {
      await updateStudent(id, { uid: edit.uid.trim().toUpperCase() || undefined, name: edit.name.trim() || undefined, guardian_email: edit.guardian_email.trim() || undefined })
      setEditId(null); fetch()
    } catch (e) { setErr(String(e)) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`Delete student ${id} and all attendance logs?`)) return
    try { await deleteStudent(id); fetch() } catch (e) { setErr(String(e)) }
  }

  const handleConsent = async (id: string, granted: boolean) => {
    try { await setConsent(id, granted); fetch() } catch (e) { setErr(String(e)) }
  }

  if (loading && students.length === 0) return <div className="page"><p style={{ opacity: 0.4 }}>Loading...</p></div>

  return (
    <div className="page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Student Roster</h2>
        <button className="btn" onClick={() => setShowAdd(!showAdd)}>{showAdd ? 'Cancel' : '+ Add Student'}</button>
      </div>
      {err && <p style={{ color: '#e53e3e', marginBottom: 8 }}>{err} <button className="btn btn-sm btn-ghost" onClick={fetch}>retry</button></p>}

      {showAdd && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input placeholder="Student ID *" value={add.student_id} onChange={e => setAdd(f => ({ ...f, student_id: e.target.value }))} style={is} />
            <input placeholder="UID *" value={add.uid} onChange={e => setAdd(f => ({ ...f, uid: e.target.value }))} style={is} />
            <input placeholder="Name" value={add.name} onChange={e => setAdd(f => ({ ...f, name: e.target.value }))} style={is} />
            <input placeholder="Guardian email" value={add.guardian_email} onChange={e => setAdd(f => ({ ...f, guardian_email: e.target.value }))} style={is} />
            <button className="btn" onClick={handleAdd} disabled={!add.student_id || !add.uid}>Save</button>
          </div>
        </div>
      )}

      {students.length === 0 ? (
        <p style={{ opacity: 0.4 }}>No students yet.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #333', textAlign: 'left' }}>
                <th style={{ padding: '6px 8px' }}>ID</th><th style={{ padding: '6px 8px' }}>UID</th>
                <th style={{ padding: '6px 8px' }}>Name</th><th style={{ padding: '6px 8px' }}>Guardian</th>
                <th style={{ padding: '6px 8px' }}>Enrolled</th><th style={{ padding: '6px 8px' }}>Consent</th>
                <th style={{ padding: '6px 8px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {students.map(s => (
                <tr key={s.student_id} style={{ borderBottom: '1px solid #1c1f27' }}>
                  {editId === s.student_id ? (
                    <>
                      <td style={{ padding: '6px 8px' }}>{s.student_id}</td>
                      <td style={{ padding: '6px 8px' }}><input value={edit.uid} onChange={e => setEdit(f => ({ ...f, uid: e.target.value }))} style={is} /></td>
                      <td style={{ padding: '6px 8px' }}><input value={edit.name} onChange={e => setEdit(f => ({ ...f, name: e.target.value }))} style={is} /></td>
                      <td style={{ padding: '6px 8px' }}><input value={edit.guardian_email} onChange={e => setEdit(f => ({ ...f, guardian_email: e.target.value }))} style={is} /></td>
                      <td style={{ padding: '6px 8px' }}>{s.enrolled ? '\u2713' : '\u2014'}</td>
                      <td style={{ padding: '6px 8px' }}>{s.face_consent ? '\u2713' : '\u2014'}</td>
                      <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                        <button className="btn btn-sm" onClick={() => handleUpdate(s.student_id)}>Save</button>
                        <button className="btn btn-sm btn-ghost" style={{ marginLeft: 4 }} onClick={() => setEditId(null)}>Cancel</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td style={{ padding: '6px 8px' }}>{s.student_id}</td>
                      <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 12 }}>{s.uid}</td>
                      <td style={{ padding: '6px 8px' }}>{s.name || '\u2014'}</td>
                      <td style={{ padding: '6px 8px', fontSize: 12 }}>{s.guardian_email || '\u2014'}</td>
                      <td style={{ padding: '6px 8px' }}>{s.enrolled ? <span className="pill" style={{ background: '#1f5c2a' }}>yes</span> : <span className="pill" style={{ background: '#333' }}>no</span>}</td>
                      <td style={{ padding: '6px 8px' }}>
                        <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                          <input type="checkbox" checked={!!s.face_consent} onChange={e => handleConsent(s.student_id, e.target.checked)} />
                          {s.face_consent ? 'granted' : 'none'}
                        </label>
                      </td>
                      <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                        <button className="btn btn-sm btn-ghost" onClick={() => startEdit(s)}>Edit</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: 4 }} onClick={() => handleDelete(s.student_id)}>Delete</button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
