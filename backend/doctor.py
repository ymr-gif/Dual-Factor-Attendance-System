"""System health check (Step 22).

Usage:
    python -m backend.doctor

Checks every subsystem and reports pass/fail with hints.
"""

import os
import sys

from . import db


def _check(ok: bool, name: str, hint: str = ""):
    icon = "✓" if ok else "✗"
    print(f"  {icon} {name}" + (f"  — {hint}" if hint else ""))


def run():
    print("nfc-scan health check\n")

    # --- Database ---
    db_ok = False
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        db_ok = True
        _check(True, "Postgres reachable")
    except Exception as e:
        _check(False, "Postgres reachable", str(e))

    if db_ok:
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM students")
                    count = cur.fetchone()[0]
            _check(True, f"students table ok ({count} rows)")
        except Exception as e:
            _check(False, "students table", str(e))

        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM attendance_logs")
                    count = cur.fetchone()[0]
            _check(True, f"attendance_logs table ok ({count} rows)")
        except Exception as e:
            _check(False, "attendance_logs table", str(e))

        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM attendance_sessions LIMIT 1")
                    cur.fetchone()
            _check(True, "attendance_sessions view ok")
        except Exception as e:
            _check(False, "attendance_sessions view", str(e))

    # --- Face model ---
    try:
        from . import face
        emb = face.encode_image(None)  # triggers lazy model load; None returns None
        _check(True, "insightface model loaded")
    except Exception as e:
        _check(False, "insightface model", str(e))

    # --- Liveness model ---
    try:
        from . import liveness
        _check(True, "liveness anti-spoof model loaded")
    except Exception as e:
        _check(False, "liveness anti-spoof model", str(e))

    # --- Camera ---
    cam_idx = os.environ.get("CAMERA_INDEX", "0")
    try:
        import cv2
        cap = cv2.VideoCapture(int(cam_idx))
        ok = cap.isOpened()
        cap.release()
        _check(ok, f"camera at index {cam_idx}", "not found — check CAMERA_INDEX")
    except Exception as e:
        _check(False, f"camera at index {cam_idx}", str(e))

    # --- Serial port ---
    port = os.environ.get("SERIAL_PORT", "/dev/ttyACM0")
    if os.path.exists(port):
        try:
            import serial
            ser = serial.Serial(port, 9600, timeout=0.5)
            ser.close()
            _check(True, f"serial port {port} ok")
        except Exception as e:
            _check(False, f"serial port {port}", str(e))
    else:
        _check(False, f"serial port {port}", "not found")

    # --- SMTP config ---
    smtp_host = os.environ.get("SMTP_HOST", "")
    email_enabled = os.environ.get("NOTIFY_EMAIL_ENABLED", "false").lower() in ("1", "true", "yes")
    if email_enabled:
        if smtp_host:
            _check(True, f"SMTP configured ({smtp_host})")
        else:
            _check(False, "SMTP config", "NOTIFY_EMAIL_ENABLED but SMTP_HOST is unset")
    else:
        _check(True, "SMTP (email disabled, console only)")

    print()


if __name__ == "__main__":
    run()
