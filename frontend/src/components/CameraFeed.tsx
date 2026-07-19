// CameraFeed (Step 35 precursor) — live MJPEG stream from /stream.mjpeg.

import { useState } from 'react'

export default function CameraFeed() {
  const [failed, setFailed] = useState(false)

  return (
    <div>
      <h2 style={{ margin: '0 0 8px', fontSize: 14, opacity: 0.6 }}>Camera</h2>
      {failed ? (
        <div
          style={{
            background: '#1c1f27',
            borderRadius: 4,
            height: 180,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: 0.5,
            fontSize: 14,
          }}
        >
          Camera unavailable
        </div>
      ) : (
        <img
          src="/stream.mjpeg"
          style={{ width: '100%', borderRadius: 4, display: 'block' }}
          onError={() => setFailed(true)}
          onLoad={() => setFailed(false)}
          alt="live camera feed"
        />
      )}
    </div>
  )
}
