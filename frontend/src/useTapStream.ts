// Live tap stream hook (Step 12). Connects to WS /ws/taps (through the Vite dev
// proxy in dev, same-origin in prod), auto-reconnects, and calls onTap per event.

import { useEffect, useRef, useState } from 'react'
import { getToken, type TapEvent } from './api'

export function useTapStream(onTap?: (e: TapEvent) => void) {
  const [connected, setConnected] = useState(false)
  const onTapRef = useRef(onTap)
  onTapRef.current = onTap

  useEffect(() => {
    const token = getToken()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/ws/taps${
      token ? `?token=${encodeURIComponent(token)}` : ''
    }`
    let ws: WebSocket | null = null
    let closed = false
    let retry: ReturnType<typeof setTimeout>

    const connect = () => {
      ws = new WebSocket(url)
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(connect, 2000)
      }
      ws.onmessage = (ev) => {
        try {
          onTapRef.current?.(JSON.parse(ev.data) as TapEvent)
        } catch {
          /* ignore malformed frame */
        }
      }
    }
    connect()

    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [])

  return { connected }
}
