// Scan steps: a light animation of one card scan going through the backend, driven by
// the backend's own step events (livelog.stage). Starts on a card read, glows on the
// step in progress with travelling dots toward the next one, holds the result for a
// few seconds, then fades. Faces with no tap are not a scan and do not start it.

import { useEffect, useRef, useState } from 'react'
import { type StageEvent } from '../api'

const ORDER = ['card', 'student', 'window', 'face', 'liveness', 'verdict', 'notify']
const LABEL: Record<string, string> = {
  card: 'Card', student: 'Student', window: 'Face window', face: 'Face match',
  liveness: 'Liveness', verdict: 'Verdict', notify: 'Guardian',
}
const GOOD = new Set(['accepted', 'flagged'])
const HOLD_MS = 6000

interface Scan { uid: string; steps: StageEvent[]; done: boolean }

export function useScanSteps() {
  const [scan, setScan] = useState<Scan | null>(null)
  const [fading, setFading] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  const onStage = (e: StageEvent) => {
    setScan((cur) => {
      if (e.stage === 'card' || !cur || cur.uid !== e.uid) {
        if (e.stage !== 'card') return cur // a late step of an older scan
        return { uid: e.uid, steps: [e], done: e.done }
      }
      return { ...cur, steps: [...cur.steps.filter((s) => s.stage !== e.stage), e], done: e.done }
    })
    clearTimeout(timer.current)
    setFading(false)
    if (e.done) timer.current = setTimeout(() => setFading(true), HOLD_MS)
  }

  useEffect(() => () => clearTimeout(timer.current), [])
  return { scan, fading, onStage }
}

function Dots({ still }: { still?: boolean }) {
  return (
    <span className={`step-dots${still ? ' still' : ''}`} aria-hidden>
      <i /><i /><i />
    </span>
  )
}

export default function ScanSteps({ scan, fading }: { scan: Scan | null; fading: boolean }) {
  if (!scan) {
    return (
      <div className="panel">
        <div className="steps" style={{ opacity: 0.4 }}>Waiting for a scan</div>
      </div>
    )
  }
  const got = [...scan.steps].sort((a, b) => ORDER.indexOf(a.stage) - ORDER.indexOf(b.stage))
  const last = got[got.length - 1]
  const next = scan.done ? null : ORDER[ORDER.indexOf(last.stage) + 1]

  return (
    <div className="panel">
      <div className={`steps${fading ? ' fading' : ''}`}>
        {got.map((s, i) => {
          const verdict = s.stage === 'verdict'
          const color = verdict ? (GOOD.has(s.text) ? '#8fd19e' : '#f08a8a') : undefined
          const active = !scan.done && s === last
          return (
            <span key={s.stage} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {i > 0 && <Dots still={scan.done} />}
              <span className={`step${active ? ' active' : ''}`} style={{ color }} title={s.ts}>
                <b>{LABEL[s.stage] ?? s.stage}</b>: {s.text}
              </span>
            </span>
          )
        })}
        {next && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Dots />
            <span className="step pending">{LABEL[next] ?? next}</span>
          </span>
        )}
      </div>
    </div>
  )
}
