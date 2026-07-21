// CamerasPanel — which cameras are attached, and which one the backend will open.
//
// Read-only, for the same reason as SerialPortsPanel: perception is the single camera
// owner and holds the device for the whole shift, so switching camera is a restart,
// not a click. Pinning is a .env edit (CAMERA_INDEX), shown in the footer here.

import { useCallback, useEffect, useState } from 'react'
import { CameraDevice, CameraList, getCameras } from '../api'

const POLL_MS = 5000

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span className="pill" style={{ background: color, fontSize: 11, whiteSpace: 'nowrap' }}>
      {text}
    </span>
  )
}

export default function CamerasPanel() {
  const [data, setData] = useState<CameraList | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    getCameras()
      .then(d => { setData(d); setErr(null) })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false))
  }, [])

  // Poll so plugging in a USB camera shows up without a manual refresh.
  useEffect(() => {
    load()
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [load])

  const rowStyle = (selected: boolean) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 10px',
    borderRadius: 4,
    marginBottom: 6,
    background: selected ? 'rgba(110, 168, 254, 0.08)' : '#12141a',
    border: `1px solid ${selected ? '#6ea8fe' : '#1c1f27'}`,
  })

  const strategy = (d: CameraList) => {
    if (!d.auto_select) return 'Off (pinned)'
    return d.prefer_external ? 'External, else built-in' : 'Built-in preferred'
  }

  // The resolved index can point at a camera the OS did not report (a pinned
  // CAMERA_INDEX, or an index we could not match); say so rather than silently
  // showing nothing highlighted.
  const resolvedIsKnown = (d: CameraList) => d.cameras.some((c: CameraDevice) => c.index === d.in_use)

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15 }}>Cameras</h3>
          <p style={{ margin: '2px 0 0', fontSize: 12, opacity: 0.5 }}>
            Video devices visible to the backend
          </p>
        </div>
        <button className="btn btn-sm btn-ghost" onClick={load}>Refresh</button>
      </div>

      {err && <p style={{ color: '#e53e3e', fontSize: 12, marginBottom: 8 }}>{err}</p>}
      {loading && !data && <p style={{ opacity: 0.4, fontSize: 13 }}>Loading...</p>}

      {data && (
        <div className="card">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, paddingBottom: 10, marginBottom: 10, borderBottom: '1px solid #1c1f27' }}>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Auto-select</div>
              <div style={{ fontSize: 13, color: data.auto_select ? '#6ea8fe' : '#888' }}>
                {strategy(data)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>CAMERA_INDEX</div>
              <code style={{ fontSize: 12 }}>{data.configured ?? 'unset'}</code>
            </div>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Backend opens</div>
              <code style={{ fontSize: 12, color: '#6ea8fe' }}>index {data.in_use}</code>
            </div>
          </div>

          {data.cameras.length === 0 ? (
            <p style={{ opacity: 0.5, fontSize: 13, margin: '4px 0' }}>
              No cameras reported by the OS.
            </p>
          ) : (
            data.cameras.map(cam => {
              const selected = cam.index === data.in_use
              return (
                <div key={`${cam.index}-${cam.name}`} style={rowStyle(selected)}>
                  <code style={{ fontSize: 12, opacity: 0.5, minWidth: 52 }}>index {cam.index}</code>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13 }}>{cam.name}</div>
                    {cam.model && (
                      <div style={{ fontSize: 11.5, opacity: 0.5, marginTop: 2, wordBreak: 'break-all' }}>
                        {cam.model}
                      </div>
                    )}
                  </div>
                  {selected && <Pill text="in use" color="#1f5c2a" />}
                  <Pill text={cam.builtin ? 'built-in' : 'external'} color="#2a2d37" />
                </div>
              )
            })
          )}

          {data.cameras.length > 0 && !resolvedIsKnown(data) && (
            <p style={{ fontSize: 11.5, opacity: 0.6, marginTop: 8 }}>
              Index {data.in_use} is not in the list above — it is used as given.
            </p>
          )}

          <p style={{ fontSize: 11.5, opacity: 0.45, marginTop: 10, marginBottom: 0, lineHeight: 1.5 }}>
            Leave <code>CAMERA_INDEX</code> unset to use an external camera when one is plugged in and
            the built-in one otherwise. Changing camera needs a backend restart. Same data from the
            shell: <code>make cameras</code>.
          </p>
        </div>
      )}
    </div>
  )
}
