import { useState } from 'react'

export default function Viewer() {
  const [failed, setFailed] = useState(false)

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#12141a' }}>
      {failed ? (
        <div style={{ color: '#555', textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>{'\u25CB'}</div>
          <div style={{ fontSize: 24, opacity: 0.6 }}>Camera offline</div>
          <div style={{ fontSize: 14, opacity: 0.3, marginTop: 8 }}>Perception not enabled or no camera detected</div>
        </div>
      ) : (
        <img
          src="/stream.mjpeg"
          onError={() => setFailed(true)}
          onLoad={() => setFailed(false)}
          style={{ maxWidth: '100%', maxHeight: '100vh', display: 'block' }}
          alt="Live camera feed"
        />
      )}
    </div>
  )
}
