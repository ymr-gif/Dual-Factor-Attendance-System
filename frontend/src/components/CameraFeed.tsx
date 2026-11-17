// CameraFeed (Step 35 precursor) — live MJPEG stream from /stream.mjpeg.

import { useState } from 'react'
import { useStreamUrl } from '../useStreamUrl'

export default function CameraFeed() {
  const [failed, setFailed] = useState(false)
  const src = useStreamUrl()

  return (
    <div className="panel" style={{ padding: 8 }}>
      {failed ? (
        <div
          style={{
            background: '#1c1f27',
            borderRadius: 4,
            height: '40vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: 0.5,
            fontSize: 14,
          }}
        >
          Camera unavailable
        </div>
      ) : src && (
        <img
          src={src}
          className="cam-img"
          onError={() => setFailed(true)}
          onLoad={() => setFailed(false)}
          alt="live camera feed"
        />
      )}
    </div>
  )
}
