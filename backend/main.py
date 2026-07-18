import time

from fastapi import FastAPI
from pydantic import BaseModel

from . import db, decision, face, liveness
from .notify import notify

app = FastAPI()


class TapRequest(BaseModel):
    uid: str
    method: str = "nfc"


@app.on_event("startup")
def on_startup():
    for attempt in range(1, 11):
        try:
            db.init_db()
            return
        except Exception as e:
            print(f"db init attempt {attempt}/10 failed: {e} — retrying in 3s")
            time.sleep(3)
    raise RuntimeError("could not reach Postgres after 10 attempts")


@app.post("/tap")
def tap(req: TapRequest):
    uid = req.uid.strip().upper()
    student = db.find_student_by_uid(uid)
    student_id = student["student_id"] if student else None

    # One webcam capture, reused for face match (1:1) and liveness. Fail-open: any
    # failure leaves the scores None and attendance is still logged; notify surfaces
    # the flags.
    face_score = face_match = None
    liveness_score = liveness_pass = None
    if student is not None and (face.enabled() or liveness.enabled()):
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
    notify(student, log)
    # Don't ship the 512-d embedding back over HTTP on every tap.
    student_out = {k: v for k, v in student.items() if k != "face_embedding"} if student else None
    return {"student": student_out, "log": log}
