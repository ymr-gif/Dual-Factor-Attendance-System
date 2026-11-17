// Live feed: the backend's own log, line by line as it prints (backend/livelog.py).
// Shows the last few lines; Expand shows more. Follows the newest line unless the
// operator has scrolled up to read. (Until 18 Nov this box listed taps; that list is
// now the History table.)

import { useEffect, useRef, useState } from 'react'
import { type LogLine } from '../api'

const SHORT = 5 // lines visible when collapsed
const LONG = 22 // lines visible when expanded
const LINE_PX = 18 // .log line-height

function tone(l: LogLine): string | undefined {
  const t = l.text
  if (l.source === 'err' || /\[ALERT\]|Traceback|Error|error|failed/.test(t)) return '#f08a8a'
  if (t.startsWith('[scan]')) return '#9cc4ff'
  if (t.startsWith('[matcher]')) return '#c9a3ff'
  if (t.startsWith('[perception]')) return '#8fb8b0'
  if (t.startsWith('[NOTIFY]') || t.startsWith('[notify]')) return '#8fd19e'
  return undefined
}

function clock(ts: string): string {
  const d = new Date(ts)
  const ms = String(d.getMilliseconds()).padStart(3, '0')
  return `${d.toLocaleTimeString([], { hour12: false })}.${ms}`
}

export default function LiveFeed({ lines, connected }: { lines: LogLine[]; connected: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const follow = useRef(true)

  useEffect(() => {
    const el = box.current
    if (el && follow.current) el.scrollTop = el.scrollHeight
  }, [lines, expanded])

  const onScroll = () => {
    const el = box.current
    if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  }

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <h2 className="panel-title" style={{ margin: 0 }}>Live Feed</h2>
        <span className="pill" style={{ background: connected ? '#1f5c2a' : '#5c4a1f', fontSize: 10 }}>
          {connected ? 'connected' : 'reconnecting...'}
        </span>
        <span style={{ flex: 1 }} />
        <button className="btn btn-sm btn-ghost" onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      <div
        ref={box}
        onScroll={onScroll}
        className="log scroll"
        style={{ height: (expanded ? LONG : SHORT) * LINE_PX + 4 }}
      >
        {lines.length === 0 ? (
          <div style={{ opacity: 0.4 }}>Waiting for the backend...</div>
        ) : (
          lines.map((l) => (
            <div key={l.seq} className="log-line" style={{ color: tone(l) }}>
              <span className="log-ts">{clock(l.ts)}</span>
              {l.text}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
