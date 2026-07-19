import { useCallback, useEffect, useRef, useState } from 'react'
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

function playTone(ctx: AudioContext, freq: number, duration: number, type: OscillatorType = 'sine', gain = 0.3) {
  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = type; osc.frequency.value = freq
  g.gain.setValueAtTime(gain, ctx.currentTime)
  g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration)
  osc.connect(g); g.connect(ctx.destination)
  osc.start(); osc.stop(ctx.currentTime + duration)
}

export default function Kiosk() {
  const [last, setLast] = useState<TapEvent | null>(null)
  const [idle, setIdle] = useState(true)
  const tm = useRef<ReturnType<typeof setTimeout>>()
  const ctxRef = useRef<AudioContext | null>(null)
  const [muted, setMuted] = useState(true)
  const [armed, setArmed] = useState(false)

  const getCtx = useCallback(() => {
    if (!ctxRef.current) ctxRef.current = new AudioContext()
    return ctxRef.current
  }, [])

  const arm = useCallback(() => {
    if (!armed) { getCtx(); setArmed(true); setMuted(false) }
  }, [armed, getCtx])

  const playVerdictSound = useCallback((v: Verdict) => {
    if (muted || !armed) return
    const ctx = getCtx()
    if (v === 'accepted') {
      playTone(ctx, 440, 0.15, 'sine', 0.25)
      setTimeout(() => playTone(ctx, 660, 0.15, 'sine', 0.25), 100)
    } else {
      playTone(ctx, 150, 0.25, 'sawtooth', 0.15)
    }
  }, [muted, armed, getCtx])

  const onTap = useCallback((e: TapEvent) => {
    setLast(e); setIdle(false)
    clearTimeout(tm.current)
    tm.current = setTimeout(() => setIdle(true), 5000)
    playVerdictSound(verdict(e.log?.status))
  }, [playVerdictSound])

  const { connected } = useTapStream(onTap)
  useEffect(() => () => clearTimeout(tm.current), [])

  if (idle) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#12141a', color: '#555', textAlign: 'center', cursor: 'pointer' }}
        onClick={arm}>
        <div>
          <div style={{ fontSize: 48, marginBottom: 16 }}>NFC</div>
          <div style={{ fontSize: 24, opacity: 0.6 }}>Tap your card</div>
          {!connected && <p style={{ fontSize: 14, opacity: 0.3, marginTop: 16 }}>connecting...</p>}
          {!armed && <p style={{ fontSize: 12, opacity: 0.25, marginTop: 12 }}>click to enable sound</p>}
        </div>
        <button
          onClick={e => { e.stopPropagation(); setMuted(!muted) }}
          style={{ position: 'fixed', top: 12, right: 12, background: 'transparent', border: '1px solid #333', color: '#888', borderRadius: 4, padding: '4px 8px', fontSize: 12, cursor: 'pointer' }}>
          {muted ? 'Unmute' : 'Mute'}
        </button>
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
      transition: 'background 0.3s', cursor: 'pointer',
    }} onClick={arm}>
      <div>
        <div style={{ fontSize: 80, fontWeight: 300, marginBottom: 8 }}>{s.icon}</div>
        <div style={{ fontSize: 48, fontWeight: 700, marginBottom: 16 }}>{name}</div>
        <div style={{ fontSize: 24, opacity: 0.7 }}>{status}</div>
        {last?.reason && <div style={{ fontSize: 16, opacity: 0.5, marginTop: 8 }}>{last.reason}</div>}
      </div>
      <button
        onClick={e => { e.stopPropagation(); setMuted(!muted) }}
        style={{ position: 'fixed', top: 12, right: 12, background: 'transparent', border: '1px solid #333', color: '#888', borderRadius: 4, padding: '4px 8px', fontSize: 12, cursor: 'pointer' }}>
        {muted ? 'Unmute' : 'Mute'}
      </button>
    </div>
  )
}
