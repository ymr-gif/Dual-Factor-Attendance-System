import asyncio
import os
import time

from datetime import datetime, timedelta, timezone

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (
    cameras, db, decision, events, face, liveness, matcher as matcher_mod,
    perception, ports, privacy,
)
from .notify import notify

# --- MJPEG live camera stream (perception.on_frame → browser) ---

# Per-client fan-out: each connected /stream.mjpeg viewer gets its own bounded queue.
# The frame sink broadcasts to all of them, so viewers no longer steal frames from
# each other (Dashboard + Viewer + Register can watch simultaneously).
_mjpeg_subscribers: set[asyncio.Queue] = set()
_mjpeg_loop: asyncio.AbstractEventLoop | None = None

# Live camera-quality snapshot for the register guided flow (Register.tsx polls
# GET /api/perception/state). Computed every frame from perception's own detections —
# no extra camera open, no image stored.
_perception_state: dict = {}
_REG_BRIGHT_LOW = float(os.environ.get("REGISTER_BRIGHT_LOW", "55"))
_REG_BRIGHT_HIGH = float(os.environ.get("REGISTER_BRIGHT_HIGH", "215"))
_REG_CENTER_MAX = float(os.environ.get("REGISTER_CENTER_MAX", "0.45"))


def _broadcast_frame(data: bytes) -> None:
    """Runs on the event-loop thread (via call_soon_threadsafe). Fan one JPEG out to
    every connected client; for a slow client, drop its oldest frame rather than block."""
    for q in _mjpeg_subscribers:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


def _on_frame_event(frame, ev):
    """Perception frame sink (called from camera thread). Draw boxes, encode JPEG,
    hand off to the async MJPEG endpoint via the event loop."""
    import cv2
    import numpy as np

    # Camera-quality snapshot (register guided flow). Cheap: reuses perception's
    # detections + the raw frame; brightness from the largest face region.
    tracks = ev.get("tracks", [])
    n_faces = len(tracks)
    face_px = 0
    brightness = None
    center_off = None
    h, w = frame.shape[:2]
    if n_faces:
        best = max(
            tracks,
            key=lambda t: min(t["bbox"][2] - t["bbox"][0], t["bbox"][3] - t["bbox"][1]),
        )
        x1, y1, x2, y2 = best["bbox"]
        face_px = int(min(x2 - x1, y2 - y1))
        region = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if region.size:
            brightness = round(float(region.mean()), 1)
        center_off = round(abs((x1 + x2) / 2 - w / 2) / (w / 2), 3) if w else None
    else:
        brightness = round(float(frame.mean()), 1)
    global _perception_state
    _perception_state = {
        "ts": ev.get("ts") or time.time(),
        "n_faces": n_faces,
        "face_px": face_px,
        "brightness": brightness,
        "center_off": center_off,
    }

    # Draw bounding boxes on the frame
    annotated = frame.copy()
    for track in ev.get("tracks", []):
        x1, y1, x2, y2 = track["bbox"]
        color = (0, 180, 0) if track.get("recognized") else (0, 165, 255)  # green / amber BGR
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{'✓' if track.get('recognized') else '?'} #{track['track_id']}"
        cv2.putText(annotated, label, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return
    loop = _mjpeg_loop
    if loop is None or not _mjpeg_subscribers:
        return  # no viewers connected — skip the fan-out entirely
    try:
        loop.call_soon_threadsafe(_broadcast_frame, jpeg.tobytes())
    except RuntimeError:
        pass  # loop closed


app = FastAPI()


def _strip_embedding(student):
    if not student:
        return None
    return {k: v for k, v in student.items() if k != "face_embedding"}


def _write_outcome(o):
    """Matcher outcome writer (Step 31): log -> notify -> broadcast. Fail-open."""
    log = db.insert_log(
        uid=o["uid"],
        student_id=o.get("student_id"),
        method=o.get("method", "nfc"),
        face_score=o.get("face_score"),
        face_match=o.get("face_match"),
        liveness_score=o.get("liveness_score"),
        liveness_pass=o.get("liveness_pass"),
        status=o["status"],
    )
    student = o.get("student")
    try:
        notify(student, log)
    except Exception as e:
        print(f"matcher notify failed: {e}")
    try:
        events.publish(
            jsonable_encoder(
                {"type": "tap", "student": _strip_embedding(student), "log": log, "reason": o.get("reason")}
            )
        )
    except Exception as e:
        print(f"matcher event publish failed: {e}")


def _post_log(student, log):
    """notify + broadcast for a synchronously-written log (fail-open on both)."""
    try:
        notify(student, log)
    except Exception as e:
        print(f"notify failed: {e}")
    try:
        events.publish(
            jsonable_encoder({"type": "tap", "student": _strip_embedding(student), "log": log})
        )
    except Exception as e:
        print(f"tap event publish failed: {e}")


# The single in-process matcher (design-notes §3: one worker, shared buffers).
matcher = matcher_mod.Matcher(outcome_sink=_write_outcome, face_search=db.search_face)

# Single shared operator token (Step 11). Unset -> /api/* is open (dev default);
# set it to lock down reads + writes. WS passes it as ?token=. CORS/hardening is
# Step 16.
OPERATOR_TOKEN = os.environ.get("OPERATOR_TOKEN", "")


class TapRequest(BaseModel):
    uid: str
    method: str = "nfc"


class StudentCreate(BaseModel):
    student_id: str
    uid: str
    name: str | None = None
    guardian_email: str | None = None


class StudentUpdate(BaseModel):
    uid: str | None = None
    name: str | None = None
    guardian_email: str | None = None


class ResolveReview(BaseModel):
    resolution: str  # 'confirmed' | 'override' | 'dismiss'


class SettingsUpdate(BaseModel):
    key: str
    value: str


def require_operator(
    authorization: str | None = Header(default=None),
    x_operator_token: str | None = Header(default=None),
):
    """Guard /api/* endpoints. Accepts `Authorization: Bearer <t>` or
    `X-Operator-Token: <t>`. When OPERATOR_TOKEN is unset, auth is disabled."""
    if not OPERATOR_TOKEN:
        return
    supplied = None
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    elif x_operator_token:
        supplied = x_operator_token.strip()
    if supplied != OPERATOR_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing operator token")


@app.on_event("startup")
def on_startup():
    for attempt in range(1, 11):
        try:
            db.init_db()
            break
        except Exception as e:
            print(f"db init attempt {attempt}/10 failed: {e} — retrying in 3s")
            time.sleep(3)
    else:
        raise RuntimeError("could not reach Postgres after 10 attempts")
    if not OPERATOR_TOKEN:
        print("WARNING: OPERATOR_TOKEN unset — /api/* is unauthenticated (dev mode)")


@app.on_event("startup")
async def _capture_loop():
    # Give events.publish() (called from the sync /tap threadpool) a handle on the
    # running loop so it can hand tap events to WebSocket subscribers safely.
    events.set_loop(asyncio.get_running_loop())


@app.on_event("startup")
async def _start_perception():
    # Continuous-flow wiring (Step 30/31). Only when perception owns the camera.
    if not perception.enabled():
        return
    perception.on_face(matcher.on_face)  # in-process face events -> matcher
    perception.on_frame(_on_frame_event)  # annotated frames -> MJPEG stream

    async def _resolve_loop():
        while True:
            await asyncio.sleep(matcher.resolve_interval)
            try:
                await asyncio.to_thread(matcher.resolve)
            except Exception as e:
                print(f"matcher resolve loop error: {e}")

    asyncio.create_task(_resolve_loop())

    # Camera-owner thread. Fail-open: perception.run exits immediately if no camera,
    # so a headless/no-cam backend still boots (taps then log card-only unverified).
    import threading

    threading.Thread(
        target=lambda: perception.run(perception._camera_frames()), daemon=True
    ).start()
    print("[main] perception + matcher + MJPEG stream started")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers auto-request /favicon.ico at the site root; we ship none, so answer
    # 204 (no content) instead of a noisy 404. The SPA sets its own tab title.
    from fastapi import Response

    return Response(status_code=204)


@app.get("/health")
def health():
    # Liveness/readiness probe for docker-compose. Reports DB reachability without
    # raising, so the endpoint answers even while Postgres is still coming up.
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        db_ok = True
    except Exception as e:
        db_ok = False
        print(f"health: db unreachable: {e}")
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@app.get("/api/setup/status")
def setup_status():
    """First-run wizard probe (Step 42). Intentionally open (no operator token) so
    the browser wizard works before a token is set. Reports what the wizard needs to
    guide a non-technical operator: DB, camera/perception, roster, token state."""
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    total = enrolled = 0
    if db_ok:
        try:
            roster = db.get_students()
            total = len(roster)
            enrolled = sum(1 for s in roster if s.get("enrolled"))
        except Exception:
            pass

    cam_fresh = False
    if perception.enabled() and _perception_state:
        cam_fresh = (time.time() - _perception_state["ts"]) < 3.0

    return {
        "db": db_ok,
        "token_required": bool(OPERATOR_TOKEN),
        "perception": {"enabled": perception.enabled(), "camera_fresh": cam_fresh},
        "students": {"total": total, "enrolled": enrolled},
        # "Ready to run" = DB up and at least one enrolled student.
        "ready": db_ok and enrolled > 0,
    }


@app.get("/metrics")
def metrics():
    from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest, Histogram

    reg = CollectorRegistry()
    c = Counter("nfc_taps_total", "Total taps processed", ["status"], registry=reg)
    g_taps = Gauge("nfc_taps_last_minute", "Taps in the last 60 s", registry=reg)
    g_camera = Gauge("nfc_camera_fps", "Camera preview FPS", registry=reg)

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(status,'unknown'), COUNT(*) FROM attendance_logs GROUP BY status")
            for status, count in cur.fetchall():
                c.labels(status=status).inc(count)

            cur.execute(
                "SELECT COUNT(*) FROM attendance_logs WHERE ts > now() - interval '60 seconds'"
            )
            g_taps.set(cur.fetchone()[0])

    from fastapi.responses import PlainTextResponse, Response

    return Response(content=generate_latest(reg), media_type="text/plain; charset=utf-8")


@app.get("/api/attendance", dependencies=[Depends(require_operator)])
def api_attendance(
    date: str | None = None,
    status: str | None = None,
    student_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return {"logs": db.get_attendance(date=date, status=status, student_id=student_id, limit=limit)}


@app.get("/api/students", dependencies=[Depends(require_operator)])
def api_students():
    return {"students": db.get_students()}


@app.get("/api/attendance/summary", dependencies=[Depends(require_operator)])
def api_attendance_summary(date: str | None = None):
    return db.get_summary(date)


@app.get("/api/attendance/sessions", dependencies=[Depends(require_operator)])
def api_attendance_sessions(
    student_id: str | None = None,
    date: str | None = None,
):
    return {"sessions": db.get_sessions(student_id=student_id, date=date)}


@app.get("/api/attendance.csv", dependencies=[Depends(require_operator)])
def api_attendance_csv(
    date: str | None = None,
    status: str | None = None,
    student_id: str | None = None,
    limit: int = 5000,
):
    import csv
    import io

    from fastapi.responses import StreamingResponse

    rows = db.get_attendance_csv(date=date, status=status, student_id=student_id, limit=limit)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "uid", "student_id", "student_name", "ts", "method", "status",
                 "face_score", "face_match", "liveness_score", "liveness_pass"])
    for r in rows:
        w.writerow([r.get(c) for c in
                     ["id", "uid", "student_id", "student_name", "ts", "method", "status",
                      "face_score", "face_match", "liveness_score", "liveness_pass"]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance.csv"},
    )


@app.get("/api/stats/today", dependencies=[Depends(require_operator)])
def api_stats_today():
    return db.get_stats_today()


@app.get("/api/config", dependencies=[Depends(require_operator)])
def api_config():
    # Read-only view of the active thresholds/flags the tap pipeline uses.
    return {
        "face": {
            "enabled": face.enabled(),
            "threshold": face.FACE_THRESHOLD,
            "det_size": face.FACE_DET_SIZE,
            "min_face_px": face.MIN_FACE_PX,
            "use_gpu": face.USE_GPU,
        },
        "liveness": {
            "enabled": liveness.enabled(),
            "threshold": liveness.LIVENESS_THRESHOLD,  # None = model argmax
        },
        "decision": {
            "enforce_2fa": decision.enforcing(),
        },
        "perception": {
            "enabled": perception.enabled(),
            "iou_thresh": perception.TRACK_IOU_THRESH,
            "max_misses": perception.TRACK_MAX_MISSES,
            "fps": perception.PERCEPTION_FPS,
        },
        "privacy": {
            "consent_required": privacy.FACE_CONSENT_REQUIRED,
            "attendance_retention_days": privacy.ATTENDANCE_RETENTION_DAYS,
            "score_retention_days": privacy.SCORE_RETENTION_DAYS,
        },
    }


@app.get("/api/settings", dependencies=[Depends(require_operator)])
def api_get_settings():
    from . import settings as s
    return {"settings": s.all_settings(), "tunable_keys": sorted(s.TUNABLE_KEYS)}


@app.put("/api/settings", dependencies=[Depends(require_operator)])
def api_set_settings(body: SettingsUpdate):
    from . import settings as s
    try:
        s.set(body.key, body.value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"key": body.key, "value": body.value}


class ConsentRequest(BaseModel):
    granted: bool


def _actor(x_operator_actor: str | None = Header(default=None)) -> str:
    # Best-effort operator identity for the audit log (shared-token auth has no real
    # user; an optional X-Operator-Actor header names the person for accountability).
    return (x_operator_actor or "operator").strip()


@app.get("/api/audit", dependencies=[Depends(require_operator)])
def api_audit(limit: int = Query(default=100, ge=1, le=1000)):
    return {"audit": db.get_audit(limit)}


# --- Phase 3: Review queue ---


@app.get("/api/review", dependencies=[Depends(require_operator)])
def api_review(limit: int = Query(default=100, ge=1, le=1000)):
    return {"queue": db.get_review_queue(limit)}


@app.post("/api/review/{review_id}/resolve", dependencies=[Depends(require_operator)])
def api_resolve_review(review_id: int, body: ResolveReview, actor: str = Depends(_actor)):
    if body.resolution not in ("confirmed", "override", "dismiss"):
        raise HTTPException(status_code=422, detail="resolution must be confirmed/override/dismiss")
    try:
        r = db.resolve_review(review_id, resolution=body.resolution, resolved_by=actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.insert_audit(actor, "review_resolve", f"review#{review_id}", detail=body.resolution)
    return r


@app.post("/api/search-face", dependencies=[Depends(require_operator)])
async def api_search_face(image: UploadFile = File(...), k: int = Query(default=5, ge=1, le=25)):
    # Cardless 1:N manual lookup (Step 33): operator uploads a face image -> encode ->
    # nearest enrolled students. No image is stored.
    import cv2
    import numpy as np

    data = await image.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="cannot decode image")
    emb = face.encode_image(img)
    if emb is None:
        raise HTTPException(status_code=422, detail=f"no usable face (need >= {face.MIN_FACE_PX}px)")
    return {"matches": db.search_face(emb, k)}


@app.get("/api/reenroll-due", dependencies=[Depends(require_operator)])
def api_reenroll_due():
    # Re-enrollment reminders (Step 33): stale-by-age or made by an older model.
    from .enroll import REENROLL_AFTER_DAYS

    cutoff = None
    if REENROLL_AFTER_DAYS > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=REENROLL_AFTER_DAYS)
    return {
        "reenroll_after_days": REENROLL_AFTER_DAYS,
        "current_model": face.MODEL_NAME,
        "due": db.stale_enrollments(cutoff=cutoff, current_model=face.MODEL_NAME),
    }


@app.post("/api/students/{student_id}/consent", dependencies=[Depends(require_operator)])
def api_set_consent(student_id: str, body: ConsentRequest, actor: str = Depends(_actor)):
    try:
        db.set_consent(student_id, body.granted)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.insert_audit(actor, "consent", student_id, detail="granted" if body.granted else "revoked")
    return {"student_id": student_id, "face_consent": body.granted}


@app.post("/api/students", dependencies=[Depends(require_operator)])
def api_create_student(body: StudentCreate, actor: str = Depends(_actor)):
    try:
        s = db.insert_student(
            student_id=body.student_id.strip().upper(),
            uid=body.uid.strip().upper(),
            name=body.name,
            guardian_email=body.guardian_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.insert_audit(actor, "create", s["student_id"], detail=f"uid={s['uid']}")
    return s


@app.patch("/api/students/{student_id}", dependencies=[Depends(require_operator)])
def api_update_student(student_id: str, body: StudentUpdate, actor: str = Depends(_actor)):
    try:
        uid = body.uid.strip().upper() if body.uid else None
    except AttributeError:
        uid = None
    try:
        s = db.update_student(
            student_id=student_id,
            uid=uid,
            name=body.name,
            guardian_email=body.guardian_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.insert_audit(actor, "update", student_id)
    return s


@app.post("/api/students/{student_id}/enroll", dependencies=[Depends(require_operator)])
async def api_enroll_student(student_id: str, images: list[UploadFile] = File(...),
                             actor: str = Depends(_actor)):
    import cv2
    import numpy as np

    from .enroll import embeddings_from_frames, enroll_student

    student = db.get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail=f"no such student {student_id}")

    frames = []
    feedback = []
    for img in images:
        data = await img.read()
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            feedback.append({"file": img.filename, "status": "rejected", "reason": "cannot decode"})
            continue
        frames.append(frame)
        feedback.append({"file": img.filename, "status": "accepted", "reason": None})

    embs = embeddings_from_frames(frames)
    if not embs:
        raise HTTPException(status_code=422, detail="no usable face in any uploaded frame")

    try:
        result = enroll_student(student_id, embs, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"student_id": student_id, "frames": feedback, "used": result["used"], "duplicate": result.get("duplicate")}


@app.delete("/api/students/{student_id}", dependencies=[Depends(require_operator)])
def api_delete_student(student_id: str, actor: str = Depends(_actor)):
    # Right-to-erasure (Step 20): drop embedding + logs, record an audit entry.
    counts = db.delete_student(student_id)
    if counts["students"] == 0 and counts["logs"] == 0:
        raise HTTPException(status_code=404, detail=f"no such student {student_id}")
    db.insert_audit(actor, "erase", student_id, detail=f"logs={counts['logs']} students={counts['students']}")
    return {"erased": student_id, **counts}


@app.websocket("/ws/taps")
async def ws_taps(websocket: WebSocket):
    # Auth via query param (?token=) — matches OPERATOR_TOKEN when it is set.
    if OPERATOR_TOKEN and websocket.query_params.get("token") != OPERATOR_TOKEN:
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    q = await events.subscribe()
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        events.unsubscribe(q)


@app.get("/stream.mjpeg")
async def stream_mjpeg():
    """Live camera feed as MJPEG stream. perception.on_frame broadcasts annotated
    JPEG frames to every connected client; this endpoint yields one client's frames
    as multipart/x-mixed-replace."""
    global _mjpeg_loop
    _mjpeg_loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=2)
    _mjpeg_subscribers.add(q)

    async def generate():
        try:
            while True:
                frame_bytes = await q.get()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
        except asyncio.CancelledError:
            pass
        finally:
            _mjpeg_subscribers.discard(q)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/cameras", dependencies=[Depends(require_operator)])
def camera_list():
    """Cameras the OS reports, plus which one the backend resolves to. Read-only:
    nothing is opened here — perception is the single camera owner, and probing a
    device would take it away mid-shift. Changing camera needs a backend restart."""
    return {
        "cameras": cameras.list_cameras(),
        "configured": cameras.configured_index(),
        "auto_select": cameras.auto_enabled(),
        "prefer_external": cameras.prefer_external(),
        "in_use": face.camera_index(),
    }


@app.get("/api/serial/ports", dependencies=[Depends(require_operator)])
def serial_ports():
    """Serial ports currently connected, best reader candidate first, plus how the
    reader would resolve one. Lets the UI show what is plugged in instead of making
    an operator guess a device path. Read-only: nothing is opened here — the reader
    owns the port, and opening it from the API would steal it mid-shift."""
    return {
        "ports": ports.list_ports_detailed(),
        "configured": ports.configured_port(),
        "auto_detect": ports.auto_enabled(),
        "would_open": ports.pick_port(),
    }


@app.get("/api/perception/state", dependencies=[Depends(require_operator)])
def perception_state():
    """Live camera-quality gate for the register guided flow. Derived from
    perception's own per-frame detections (no extra camera open, no image stored).
    Returns `ready` + a human `reason` so the frontend can gate the capture button."""
    if not perception.enabled():
        return {"enabled": False, "ready": False,
                "reason": "Perception off — live camera gate unavailable"}
    st = _perception_state
    if not st:
        return {"enabled": True, "ready": False, "reason": "Waiting for camera…"}
    age = round(time.time() - st["ts"], 2)
    base = {
        "enabled": True,
        "n_faces": st["n_faces"],
        "face_px": st["face_px"],
        "brightness": st["brightness"],
        "min_face_px": face.MIN_FACE_PX,
        "age": age,
    }
    n, b = st["n_faces"], st["brightness"]
    if age > 2.0:
        return {**base, "ready": False, "reason": "Camera feed stale"}
    if n == 0:
        return {**base, "ready": False, "reason": "No face detected — step in front of the camera"}
    if n > 1:
        return {**base, "ready": False, "reason": f"{n} people in frame — only one at a time"}
    if st["face_px"] < face.MIN_FACE_PX:
        return {**base, "ready": False, "reason": "Move closer to the camera"}
    if b is not None and b < _REG_BRIGHT_LOW:
        return {**base, "ready": False, "reason": "Not enough light on your face"}
    if b is not None and b > _REG_BRIGHT_HIGH:
        return {**base, "ready": False, "reason": "Too bright / backlit — reduce the light"}
    if st["center_off"] is not None and st["center_off"] > _REG_CENTER_MAX:
        return {**base, "ready": False, "reason": "Center yourself in the frame"}
    return {**base, "ready": True, "reason": "Ready — looking good"}


@app.post("/tap")
def tap(req: TapRequest):
    uid = req.uid.strip().upper()
    student = db.find_student_by_uid(uid)
    student_id = student["student_id"] if student else None
    student_out = _strip_embedding(student)

    # Continuous flow (Step 31): perception owns the camera, so /tap enqueues the tap
    # and acks immediately; the matcher writes the verdict when the association window
    # closes. Unknown card / un-enrolled student are resolved synchronously (no face
    # to wait for).
    if perception.enabled():
        if student is None:
            log = db.insert_log(uid=uid, student_id=None, method=req.method, status=decision.UNREGISTERED)
            _post_log(student, log)
            return {"status": "logged", "student": None, "log": log}
        ref = student.get("face_embedding")
        # No reference, or consent not granted (Step 20) -> fail-open, card-only NFC log.
        if ref is None or not privacy.consent_ok(student):
            log = db.insert_log(uid=uid, student_id=student_id, method=req.method, status=decision.UNVERIFIED)
            _post_log(student, log)
            return {"status": "logged", "student": student_out, "log": log}
        tap_id = matcher.add_tap(uid, student_id, ref, student=student)
        return {"status": "queued" if tap_id else "debounced", "uid": uid, "student": student_out}

    # One webcam capture, reused for face match (1:1) and liveness. Fail-open: any
    # failure leaves the scores None and attendance is still logged; notify surfaces
    # the flags.
    face_score = face_match = None
    liveness_score = liveness_pass = None
    # Consent gate (Step 20): skip face/liveness when the student hasn't consented and
    # the policy is on; the tap still logs NFC-only (unverified).
    if student is not None and privacy.consent_ok(student) and (face.enabled() or liveness.enabled()):
        probe = face.capture_probe()  # Probe(frame, bbox, embedding) or None
        if probe is not None:
            if face.enabled() and student.get("face_embedding") is not None:
                face_score = face.cosine(probe.embedding, student["face_embedding"])
                face_match = face_score >= face.FACE_THRESHOLD
            if liveness.enabled():
                liveness_score, liveness_pass = liveness.assess(probe.frame, probe.bbox)

    # Collapse the factors into one attendance verdict (Step 9). ENFORCE_2FA off ->
    # a failed factor is 'flagged' but still logged as present; on -> 'rejected'.
    status = decision.decide(student, face_match, liveness_pass)

    log = db.insert_log(
        uid=uid,
        student_id=student_id,
        method=req.method,
        face_score=face_score,
        face_match=face_match,
        liveness_score=liveness_score,
        liveness_pass=liveness_pass,
        status=status,
    )
    _post_log(student, log)
    return {"student": student_out, "log": log}


# --- SPA serving (Step 12). Mount the built frontend at /app *only if it exists*,
# so the backend still boots before the frontend is built. Client-side routes
# (e.g. /app/kiosk) fall back to index.html. ---
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
_DIST_REAL = os.path.realpath(_DIST)
if os.path.isdir(_DIST):
    app.mount("/app/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/app")
    @app.get("/app/{path:path}")
    def spa(path: str = ""):
        if path:
            # Resolve against the dist root and refuse anything that escapes it
            # (path traversal via ../). On a miss, fall through to index.html.
            candidate = os.path.realpath(os.path.join(_DIST_REAL, path))
            if (
                (candidate == _DIST_REAL or candidate.startswith(_DIST_REAL + os.sep))
                and os.path.isfile(candidate)
            ):
                return FileResponse(candidate)  # favicon, etc.
        return FileResponse(os.path.join(_DIST_REAL, "index.html"))  # SPA fallback
else:
    print(f"SPA not mounted: {_DIST} missing (run `make web-build`)")
