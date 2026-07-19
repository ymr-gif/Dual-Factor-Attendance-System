import { useEffect, useRef, useState } from 'react'
import { type TapEvent } from '../api'
import { useTapStream } from '../useTapStream'

type Verdict = 'accepted' | 'warning' | 'rejected'

const VS: Record<Verdict, { bg: string; icon: string }> = {
  accepted: { bg: '#1a3a1a', icon: '\u2713' },
  warning: { bg: '#3a351a', icon: '!' },
  rejected: { bg: '#3a1a1a', icon: '\u2717' },
}

function verdict(s: string | null | undefined): Verdict {
  if (s === 'accepted') return 'accepted'
  if (s === 'flagged' || s === 'unverified' || s === 'no_face') return 'warning'
  return 'rejected'
}

export default function Kiosk() {
  const [last, setLast] = useState<TapEvent | null>(null)
  const [idle, setIdle] = useState(true)
  const tm = useRef<ReturnType<typeof setTimeout>>()

  const onTap = (e: TapEvent) => {
    setLast(e); setIdle(false)
    clearTimeout(tm.current)
    tm.current = setTimeout(() => setIdle(true), 5000)
  }

  const { connected } = useTapStream(onTap)
  useEffect(() => () => clearTimeout(tm.current), [])

  if (idle) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#12141a', color: '#555', textAlign: 'center' }}>
        <div>
          <div style={{ fontSize: 48, marginBottom: 16 }}>NFC</div>
          <div style={{ fontSize: 24, opacity: 0.6 }}>Tap your card</div>
          {!connected && <p style={{ fontSize: 14, opacity: 0.3, marginTop: 16 }}>connecting...</p>}
        </div>
      </div>
    )
  }

  const status = last?.log?.status ?? 'unknown'
  const v = verdict(status)
  const s = VS[v]
  const name = last?.student?.name || last?.log?.uid || 'Unknown'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', background: s.bg, color: '#e6e8ee', textAlign: 'center',
      transition: 'background 0.3s',
    }}>
      <div>
        <div style={{ fontSize: 80, fontWeight: 300, marginBottom: 8 }}>{s.icon}</div>
        <div style={{ fontSize: 48, fontWeight: 700, marginBottom: 16 }}>{name}</div>
        <div style={{ fontSize: 24, opacity: 0.7 }}>{status}</div>
        {last?.reason && <div style={{ fontSize: 16, opacity: 0.5, marginTop: 8 }}>{last.reason}</div>}
      </div>
    </div>
  )
}
