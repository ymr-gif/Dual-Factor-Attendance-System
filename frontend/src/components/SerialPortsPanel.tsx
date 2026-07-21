// SerialPortsPanel — what is plugged in, and which port the NFC reader will open.
//
// Read-only by design: the reader reads SERIAL_PORT from the environment at start
// and owns the device for the whole shift, so the UI reports rather than rebinds.
// Pinning a port is a .env edit + reader restart (shown in the footer here).

import { useCallback, useEffect, useState } from 'react'
import { getSerialPorts, SerialPort, SerialPorts } from '../api'

const POLL_MS = 5000

function hexId(port: SerialPort): string | null {
  if (port.vid === null) return null
  const h = (n: number) => n.toString(16).padStart(4, '0')
  return `${h(port.vid)}:${h(port.pid ?? 0)}`
}

function characteristics(port: SerialPort): string {
  const bits: string[] = []
  if (port.vendor_name) bits.push(port.vendor_name)
  else if (port.manufacturer) bits.push(port.manufacturer)
  if (port.product) bits.push(port.product)
  else if (port.description) bits.push(port.description)
  const id = hexId(port)
  if (id) bits.push(id)
  return bits.join('  ·  ') || 'no USB metadata'
}

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span className="pill" style={{ background: color, fontSize: 11, whiteSpace: 'nowrap' }}>
      {text}
    </span>
  )
}

export default function SerialPortsPanel() {
  const [data, setData] = useState<SerialPorts | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    getSerialPorts()
      .then(d => { setData(d); setErr(null) })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false))
  }, [])

  // Poll so hot-plugging a board shows up without a manual refresh.
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

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15 }}>Serial ports</h3>
          <p style={{ margin: '2px 0 0', fontSize: 12, opacity: 0.5 }}>
            USB devices visible to the NFC reader
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
              <div style={{ fontSize: 11, opacity: 0.5 }}>Auto-detect</div>
              <div style={{ fontSize: 13, color: data.auto_detect ? '#6ea8fe' : '#888' }}>
                {data.auto_detect ? 'On' : 'Off (pinned)'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>SERIAL_PORT</div>
              <code style={{ fontSize: 12 }}>{data.configured ?? 'unset'}</code>
            </div>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Reader opens</div>
              <code style={{ fontSize: 12, color: data.would_open ? '#6ea8fe' : '#888' }}>
                {data.would_open ?? 'nothing found'}
              </code>
            </div>
          </div>

          {data.ports.length === 0 ? (
            <p style={{ opacity: 0.5, fontSize: 13, margin: '4px 0' }}>
              No serial ports found — is the board plugged in?
            </p>
          ) : (
            data.ports.map(port => {
              const selected = port.device === data.would_open
              return (
                <div key={port.device} style={rowStyle(selected)}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <code style={{ fontSize: 12.5, wordBreak: 'break-all' }}>{port.device}</code>
                    <div style={{ fontSize: 11.5, opacity: 0.55, marginTop: 2 }}>
                      {characteristics(port)}
                    </div>
                  </div>
                  {selected && <Pill text="in use" color="#1f5c2a" />}
                  {port.likely_board
                    ? <Pill text="likely board" color="#2a2d37" />
                    : <Pill text="unlikely" color="transparent" />}
                </div>
              )
            })
          )}

          {data.configured && data.would_open && data.configured !== data.would_open && (
            <p style={{ fontSize: 11.5, opacity: 0.6, marginTop: 8 }}>
              SERIAL_PORT is not connected — auto-detect fell back to the port above.
            </p>
          )}

          <p style={{ fontSize: 11.5, opacity: 0.45, marginTop: 10, marginBottom: 0, lineHeight: 1.5 }}>
            Leave <code>SERIAL_PORT</code> unset to follow the board across USB sockets. To pin one,
            set it in <code>.env</code> and restart the reader. Same data from the shell:{' '}
            <code>make ports</code>.
          </p>
        </div>
      )}
    </div>
  )
}
