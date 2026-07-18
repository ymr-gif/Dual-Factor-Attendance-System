import json
import os
import time

import requests
import serial

PORT = os.environ.get("SERIAL_PORT", "/dev/ttyACM0")
BAUD = int(os.environ.get("SERIAL_BAUD", "9600"))
TAP_URL = os.environ.get("TAP_URL", "http://localhost:8000/tap")
QUEUE_PATH = os.environ.get(
    "FAILED_TAPS_QUEUE",
    os.path.join(os.path.dirname(__file__), "failed_taps.jsonl"),
)
RECONNECT_DELAY = 3


def post_tap(uid: str) -> bool:
    try:
        resp = requests.post(TAP_URL, json={"uid": uid}, timeout=5)
        print(resp.status_code, resp.json())
        return resp.ok
    except requests.RequestException as e:
        print(f"post failed: {e}")
        return False


def queue_failed_tap(uid: str):
    with open(QUEUE_PATH, "a") as f:
        f.write(json.dumps({"uid": uid, "queued_at": time.time()}) + "\n")


def flush_queue():
    if not os.path.exists(QUEUE_PATH):
        return
    with open(QUEUE_PATH) as f:
        lines = [l for l in f.readlines() if l.strip()]
    if not lines:
        return
    remaining = []
    for line in lines:
        entry = json.loads(line)
        if not post_tap(entry["uid"]):
            remaining.append(line)
    with open(QUEUE_PATH, "w") as f:
        f.writelines(remaining)
    if len(remaining) < len(lines):
        print(f"flushed {len(lines) - len(remaining)} queued tap(s), {len(remaining)} still pending")


def open_serial():
    while True:
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            print(f"listening on {PORT} @ {BAUD}")
            return ser
        except serial.SerialException as e:
            print(f"could not open {PORT}: {e} — retrying in {RECONNECT_DELAY}s")
            time.sleep(RECONNECT_DELAY)


def main():
    ser = open_serial()
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
        except serial.SerialException as e:
            print(f"serial read failed: {e} — reconnecting")
            ser.close()
            ser = open_serial()
            continue

        if not line.startswith("UID:"):
            continue
        uid = line[len("UID:"):].strip()
        if not uid:
            continue

        print(f"tap uid={uid}")
        flush_queue()
        if not post_tap(uid):
            queue_failed_tap(uid)


if __name__ == "__main__":
    main()
