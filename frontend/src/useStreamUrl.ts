// Camera stream URL hook. /stream.mjpeg is loaded by an <img>, which cannot send a
// header, so whatever opens it has to sit in the URL. With an operator token set that
// is a short-lived ticket from POST /api/stream-ticket, never the token itself. With no
// token the backend is in open mode and the plain path works.

import { useEffect, useState } from 'react'
import { getStreamTicket, getToken } from './api'

const STREAM_PATH = '/stream.mjpeg'

// Returns null until the URL is known. Render the <img> only once it is not null.
export function useStreamUrl(): string | null {
  const [url, setUrl] = useState<string | null>(() => (getToken() ? null : STREAM_PATH))

  useEffect(() => {
    if (!getToken()) return
    let gone = false
    getStreamTicket()
      .then((ticket) => {
        if (!gone) setUrl(`${STREAM_PATH}?ticket=${encodeURIComponent(ticket)}`)
      })
      .catch(() => {
        // No ticket (wrong token, backend down): let the <img> fail on the bare path
        // so each page shows its own "camera offline" state.
        if (!gone) setUrl(STREAM_PATH)
      })
    return () => {
      gone = true
    }
  }, [])

  return url
}
