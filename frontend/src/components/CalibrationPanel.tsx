// CalibrationPanel — the web-UI counterpart to `python -m backend.calibrate`.
//
// Read-only: shows the logged score distribution (face or liveness) so a threshold
// can be picked from measured data instead of a guess. Setting the threshold itself
// happens in the tunable-settings box above (liveness_threshold / nothing for face,
// which only reads FACE_THRESHOLD from .env).

import { useCallback, useEffect, useState } from 'react'
import { Calibration, getCalibration } from '../api'

const METRICS: ('liveness' | 'face')[] = ['liveness', 'face']

export default function CalibrationPanel() {
  const [metric, setMetric] = useState<'liveness' | 'face'>('liveness')
  const [data, setData] = useState<Calibration | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback((m: 'liveness' | 'face') => {
    setLoading(true); setErr(null)
    getCalibration(m)
      .then(d => setData(d))
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(metric) }, [metric, load])

  const maxCount = data?.histogram?.length ? Math.max(...data.histogram.map(b => b.count), 1) : 1

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 15 }}>Calibration</h3>
          <p style={{ margin: '2px 0 0', fontSize: 12, opacity: 0.5 }}>
            Logged score distribution — pick a threshold from this, then set it above
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {METRICS.map(m => (
            <button key={m} className={`btn btn-sm ${m === metric ? '' : 'btn-ghost'}`} onClick={() => setMetric(m)}>
              {m}
            </button>
          ))}
          <button className="btn btn-sm btn-ghost" onClick={() => load(metric)}>Refresh</button>
        </div>
      </div>

      {err && <p style={{ color: '#e53e3e', fontSize: 12, marginBottom: 8 }}>{err}</p>}
      {loading && !data && <p style={{ opacity: 0.4, fontSize: 13 }}>Loading...</p>}

      {data && !loading && (
        <div className="card">
          {data.count === 0 ? (
            <p style={{ opacity: 0.5, fontSize: 13, margin: '4px 0' }}>
              No {metric} scores logged yet — tap a few students first.
            </p>
          ) : (
            <>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, paddingBottom: 10, marginBottom: 10, borderBottom: '1px solid #1c1f27' }}>
                <div>
                  <div style={{ fontSize: 11, opacity: 0.5 }}>Scored taps</div>
                  <div style={{ fontSize: 13 }}>{data.count}</div>
                </div>
                {data.labels && (
                  <div>
                    <div style={{ fontSize: 11, opacity: 0.5 }}>{data.labels.pos} / {data.labels.neg}</div>
                    <div style={{ fontSize: 13 }}>{data.pos} / {data.neg}</div>
                  </div>
                )}
                <div>
                  <div style={{ fontSize: 11, opacity: 0.5 }}>Min / mean / max</div>
                  <code style={{ fontSize: 12 }}>
                    {data.min?.toFixed(3)} / {data.mean?.toFixed(3)} / {data.max?.toFixed(3)}
                  </code>
                </div>
                <div>
                  <div style={{ fontSize: 11, opacity: 0.5 }}>Threshold in force</div>
                  <code style={{ fontSize: 12, color: data.threshold === null ? '#888' : '#6ea8fe' }}>
                    {data.threshold === null ? 'unset (argmax verdict)' : data.threshold}
                  </code>
                </div>
              </div>

              {data.histogram && (
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 90, marginBottom: 6 }}>
                  {data.histogram.map(b => {
                    const atThreshold = data.threshold !== null && data.threshold >= b.low && data.threshold < b.high
                    return (
                      <div key={b.low} style={{ flex: 1, textAlign: 'center' }} title={`${b.low.toFixed(1)}-${b.high.toFixed(1)}: ${b.count}`}>
                        <div style={{
                          height: Math.max((b.count / maxCount) * 70, b.count > 0 ? 3 : 0),
                          background: atThreshold ? '#6ea8fe' : '#3a3f4d',
                          borderRadius: 2,
                        }} />
                        <div style={{ fontSize: 9, opacity: 0.45, marginTop: 4 }}>{b.low.toFixed(1)}</div>
                        <div style={{ fontSize: 10, opacity: 0.7 }}>{b.count}</div>
                      </div>
                    )
                  })}
                </div>
              )}

              {data.percentiles && (
                <p style={{ fontSize: 11, opacity: 0.5, marginTop: 10, marginBottom: 0 }}>
                  p5={data.percentiles['5']?.toFixed(3)}  p25={data.percentiles['25']?.toFixed(3)}  p50={data.percentiles['50']?.toFixed(3)}  p75={data.percentiles['75']?.toFixed(3)}  p95={data.percentiles['95']?.toFixed(3)}
                </p>
              )}
            </>
          )}

          <p style={{ fontSize: 11.5, opacity: 0.45, marginTop: 10, marginBottom: 0, lineHeight: 1.5 }}>
            Aim a threshold below the {data.labels?.pos ?? 'genuine'} cluster's low tail and above the{' '}
            {data.labels?.neg ?? 'spoof'} scores. Same data from the shell:{' '}
            <code>python -m backend.calibrate --metric {metric}</code>.
          </p>
        </div>
      )}
    </div>
  )
}
