// Placeholder kiosk screen (Step 12). Fullscreen tap feedback lands later
// (superseded by the boxes-only viewer, Step 35). Unauthenticated LAN route.

import { useState } from 'react'
import { type TapEvent } from '../api'
import { useTapStream } from '../useTapStream'

export default function Kiosk() {
  const [last, setLast] = useState<TapEvent | null>(null)
  useTapStream(setLast)

  return (
    <div
      className="wrap"
      style={{ textAlign: 'center', paddingTop: 80, minHeight: '80vh' }}
    >
      <h1 style={{ fontSize: 48 }}>
        {last ? last.student?.name ?? last.log.uid : 'Tap your card'}
      </h1>
      {last && (
        <p style={{ fontSize: 24, opacity: 0.8 }}>
          {last.log.status ?? 'logged'}
        </p>
      )}
      <p style={{ marginTop: 40, opacity: 0.5 }}>Kiosk scaffold (Step 12).</p>
    </div>
  )
}
