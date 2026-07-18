# Face verification (Step 6) — runbook

1:1 face match as a second factor. NFC identifies the student (UID → `student_id`);
the face check confirms the person holding the card is that student. Guards against
cloned/borrowed cards. Built and **verified live on 2026-07-10** (see [Verification record](#verification-record)).

- Library: **InsightFace `buffalo_l`** (ArcFace R50, 512-d), CPU via `onnxruntime`.
- Code: `backend/face.py`, `backend/enroll.py`, `backend/calibrate.py`; wired into `backend/main.py:/tap`.

## Where the face is stored

**A numeric embedding, not an image.**

- Column `students.face_embedding`, type `vector(512)` (pgvector), one row per student.
- DB: container `nfc-scan-postgres` (port 5433), persistent volume `nfc-scan-pgdata` — survives restarts.
- **No photo is written to disk.** Enrollment frames are encoded to the vector, then discarded.
- The embedding is one-way: it verifies a face but the original image can't be reconstructed from it.
- The `buffalo_l` model files under `~/.insightface/models/buffalo_l/` are the recognition
  network — not anyone's face data.

Check who's enrolled:
```
docker exec nfc-scan-postgres psql -U attendance -d attendance \
  -c "SELECT student_id, face_embedding IS NOT NULL AS enrolled FROM students;"
```

## Enrollment

Averages 3–5 shots into one re-normalized embedding (bigger real-world accuracy win
than a single photo). Stored via `db.set_face_embedding`.

```
python -m backend.enroll S001 --capture 5                  # from the webcam (prompts per shot)
python -m backend.enroll S001 --images a.jpg b.jpg c.jpg   # from files
```

Shots with no usable face (smaller than `MIN_FACE_PX`, or none detected) are skipped with a
warning; it aborts if zero usable shots remain and warns if fewer than 3.

## How a tap verifies

`backend/main.py:tap()`, after UID → student lookup, before logging:

1. Skip entirely unless face match is enabled **and** the student has an enrolled embedding.
2. `face.capture_probe()` — grab `CAMERA_PROBE_FRAMES` webcam frames (after warmup). **Detection
   runs on every frame (cheap); recognition runs once, on the largest face that clears
   `MIN_FACE_PX`.** Largest-face rule stops a bystander at the kiosk from hijacking the match,
   and running recognition on only that one face makes tap cost independent of how many people
   are in view. Camera is opened/released per tap.
3. `face_score = cosine(probe, reference)`; `face_match = face_score >= FACE_THRESHOLD`.
4. Both values written to `attendance_logs` (`face_score REAL`, `face_match BOOLEAN`).

**Fail-open.** No camera, no detected face, or no enrolled reference → `face_score`/`face_match`
stay NULL and attendance is still logged; `notify` prints a warning (`⚠ FACE MISMATCH` on a
false match, `⚠ face unverified` when an enrolled student produced no usable probe). A strict
cutoff catches impostors while false rejects only raise a flag — never block attendance.

## Threshold & calibration

Default `FACE_THRESHOLD = 0.5` (cosine) is deliberately conservative. Tune from real logged
scores rather than guessing:

```
python -m backend.calibrate            # all scored taps
python -m backend.calibrate --days 7   # last 7 days
```

Prints count, min/mean/max, percentiles, and a histogram. Aim the threshold below the genuine
cluster's low tail and above the impostor scores. Read-only; no writes.

## Configuration (env vars)

All optional; set on the `nfc-scan-backend` systemd unit.

| Var | Default | Meaning |
|-----|---------|---------|
| `FACE_MATCH_ENABLED` | `true` | `false` runs the backend headless (no webcam needed) |
| `CAMERA_INDEX` | `0` | webcam device index (`/dev/videoN`) |
| `FACE_THRESHOLD` | `0.5` | cosine cutoff for a match |
| `CAMERA_WARMUP_FRAMES` | `5` | frames discarded before capture (sensor settle) |
| `CAMERA_PROBE_FRAMES` | `5` | best-of-N frames per tap (lower = faster tap) |
| `MIN_FACE_PX` | `80` | min face bbox side; smaller faces ignored |
| `FACE_DET_SIZE` | `320` | detector input size. 320 suits a close kiosk face (~14fps detect on CPU); raise (448/640) for far/small faces at a speed cost |
| `USE_GPU` | `false` | run detection/recognition/liveness on CUDA GPU; auto-falls back to CPU if unavailable (see Performance & GPU) |

InsightFace downloads `buffalo_l` once (~300 MB) to `~/.insightface` on first use.

## Performance & GPU

The pipeline is CPU-first and tuned so tap latency doesn't grow with crowd size:

- **Detect every frame (cheap), recognize once (largest face only).** `app.get()` would run the
  512-d embedding on *every* detected face; we split detection from recognition so the ~360ms
  ArcFace step runs a single time per tap. A crowd in frame no longer multiplies cost.
- **Lean model pack** — `buffalo_l` loaded with `allowed_modules=['detection','recognition']`
  (landmark + gender/age dropped), all CPU cores (`OMP_NUM_THREADS`).
- **`FACE_DET_SIZE=320`** — detection ~72ms (~14fps) vs ~277ms at 640; ample for a close face.

Measured on this 4-core CPU box: detection ~72ms, recognition ~360ms (once/tap), liveness ~10ms
→ **~0.7s per tap, crowd-independent**; live preview ~10–14fps.

**GPU switch.** One env var, `USE_GPU`, drives both face and liveness. Default `false` (CPU). If
set `true` it uses `CUDAExecutionProvider` (InsightFace `ctx_id=0`), and if CUDA isn't available
it prints a warning and falls back to CPU — safe to preset before the hardware is in place.
To enable on a CUDA machine (e.g. after migrating to the RTX 1050 box):

```
pip install onnxruntime-gpu                     # plus nvidia driver + CUDA/cuDNN
systemctl --user edit nfc-scan-backend          # add: Environment=USE_GPU=true
systemctl --user restart nfc-scan-backend
```

Expect roughly 5–10× on the recognition step (the dominant per-tap cost).

## Camera preview (setup aid)

`python -m backend.preview` opens a live diagnostic window (not part of the tap flow): per-frame
face box + pixel size (green = clears `MIN_FACE_PX`, orange = TOO SMALL), the LIVE/SPOOF liveness
score, and — with `--match S001` — the cosine vs an enrolled reference. Use it to aim/light the
kiosk camera. Press `q`/`Esc` to quit. **It holds the webcam while open**, so close it before
tapping (only one process can open the camera). Detection runs every frame; recognition/liveness
are throttled (`--every N`, default 3) to keep it smooth on CPU. Needs the GUI OpenCV + a display.

## Hardware

USB webcam on the backend laptop. Confirmed at `/dev/video0` (640×480). If the camera moves
and enumerates as `video1`, set `CAMERA_INDEX=1` on the backend unit. The shell/service user
must be in the `video` group.

## Troubleshooting

- **`no usable face`** — subject too far (raise size / lower `MIN_FACE_PX`), poor light, or
  wrong `CAMERA_INDEX`. Diagnose: open the index in `cv2.VideoCapture` and print detected bbox sizes.
- **`can't open camera by index`** — device busy or wrong index; only one process holds the cam.
- **Every enrolled tap flags `face unverified`** — camera not reachable from the service; check
  `CAMERA_INDEX`, `video` group membership, and that nothing else holds the device.
- **First face tap is slow** — one-time model load into the service process; cached afterward.

## Known limitation

Face match alone does **not** stop a printed photo or phone screen held to the camera — that's
**passive liveness (Step 7, MiniFASNet)**, which fills the existing `liveness_score` column.
Buddy-punch mitigation (2FA enforced) depends on face + liveness together.

## Verification record

Verified live on **2026-07-10** with the attached USB webcam:

| Check | Result |
|-------|--------|
| Webcam | `/dev/video0`, opens at 640×480 |
| `capture_probe()` | 512-d embedding, self-cosine 1.0 |
| Schema migration | `vector` ext + `face_embedding vector(512)`, `face_score`, `face_match` applied on restart |
| Enroll S001 (3 live shots) | stored, read back as numpy `(512,)` via `register_vector` |
| Genuine match | score **0.86**, `face_match=true`, no warning |
| Impostor (different reference) | score **0.018**, `face_match=false`, `⚠ FACE MISMATCH`, still logged (fail-open) |
| No reference / no camera | scores NULL, attendance still logged, no crash |
| `calibrate.py` | genuine ~0.80–0.86 vs impostor 0.018 — 0.5 threshold sits cleanly in the gap |
