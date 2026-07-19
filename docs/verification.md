# Verification runbook (Steps 10–33)

How to confirm each built feature works. Ordered so you can run top-to-bottom.
`[CPU]` steps verify fully here; `[GPU/HW]` steps verify their *logic* — real
throughput / live-camera acceptance waits for the RTX box + devices.

Prereqs: Postgres up, backend importable. Two ways to run the backend:

```bash
# A) docker (Step 10)
cp .env.example .env
make up                       # db + backend
curl -s localhost:8001/health # {"status":"ok","db":true}

# B) local (systemd unit already present on the dev box)
systemctl --user restart nfc-scan-backend
```

Shorthands used below:

```bash
BASE=http://localhost:8001
PY=/home/scylla/.pyenv/versions/3.11.8/bin/python   # the env the backend uses
# If OPERATOR_TOKEN is set, add:  -H "X-Operator-Token: $OPERATOR_TOKEN"
```

---

## Step 10 — one-command setup

```bash
docker compose config -q && echo "compose valid"
make help                              # lists targets
curl -s $BASE/health                   # {"status":"ok","db":true}
```
✅ Pass: compose validates, `/health` returns `db:true`.

---

## Step 11 — operator API + live tap stream

```bash
curl -s $BASE/api/config      | $PY -m json.tool
curl -s $BASE/api/students    | $PY -m json.tool     # no face_embedding in payload
curl -s $BASE/api/stats/today | $PY -m json.tool
curl -s "$BASE/api/attendance?limit=5" | $PY -m json.tool
```

Live WebSocket event on a tap:

```bash
$PY - <<'PY'
import asyncio, json, urllib.request, websockets
async def main():
    async with websockets.connect("ws://localhost:8001/ws/taps") as ws:
        await asyncio.sleep(0.3)
        urllib.request.urlopen(urllib.request.Request(
            "http://localhost:8001/tap", data=json.dumps({"uid":"C3BE343A"}).encode(),
            headers={"Content-Type":"application/json"}, method="POST")).read()
        print("WS event:", json.loads(await asyncio.wait_for(ws.recv(), 20))["type"])
asyncio.run(main())
PY
```

Auth (only when `OPERATOR_TOKEN` is set): a request **without** the token → `401`,
**with** it → `200`.

✅ Pass: every endpoint returns JSON, no embeddings leak, a `tap` event streams.

---

## Step 12 — SPA scaffold

```bash
make web-build                         # produces frontend/dist
curl -s $BASE/app | grep -o '<title>.*</title>'      # served by backend
curl -s -o /dev/null -w "%{http_code}\n" $BASE/app/kiosk   # 200 (SPA fallback)

# Path-traversal must NOT leak (should return index.html, not passwd):
curl -s "$BASE/app/..%2f..%2f..%2f..%2f..%2fetc%2fpasswd" | grep -q "root:.*:0:0" \
  && echo "LEAK!" || echo "traversal blocked"

# Dev proxy:
make web-dev    # then open http://localhost:5173/app/ ; /health + /api proxy to :8001
```
✅ Pass: `/app` serves the shell, `/app/kiosk` falls back, traversal blocked, dev proxy reaches the API.

---

## Step 30 — perception service `[GPU/HW]` (logic verified on CPU)

Deterministic tracker + once-per-track recognition, no camera/models needed:

```bash
PYTHONPATH=. $PY - <<'PY'
import numpy as np
from backend import face, perception
face.embed = lambda frame, det: np.ones(512, np.float32)   # stub recognition
Det = face.Detection
scripts = [[Det((100,100,220,260),None,.9)],               # A
           [Det((108,100,228,260),None,.9)],
           [Det((116,100,236,260),None,.9)],
           [Det((124,100,244,260),None,.9), Det((400,100,520,260),None,.9)],  # A + B
           [Det((418,100,538,260),None,.9)]]                # only B
perception.liveness.LIVENESS_ENABLED = False
idx=[0]; face.detect = lambda f: scripts[idx[0]]
frames=[]; faces=[]
perception.on_frame(frames.append); perception.on_face(faces.append)
tr = perception.FaceTracker(max_misses=1)
for i in range(len(scripts)):
    idx[0]=i; perception.process_frame(np.zeros((480,640,3),np.uint8), tr)
print("track ids/frame:", [[t["track_id"] for t in fe["tracks"]] for fe in frames])
print("recognized tracks:", [fe["track_id"] for fe in faces])   # expect [1, 2]
PY
```
✅ Pass: face A keeps id 1 across frames, B is id 2, recognition fires once per track.
Offline video: `PERCEPTION_SOURCE=clip.mp4 PYTHONPATH=. $PY -m backend.perception`.

---

## Step 31 — tap↔face matcher `[CPU]`

Edge-case suite (no DB / camera — injected clock + sink):

```bash
PYTHONPATH=. $PY - <<'PY'
import numpy as np
from backend.matcher import Matcher
from backend import decision
D=512
def u(i): v=np.zeros(D,np.float32); v[i]=1; return v
A,B=u(0),u(1)
def search(e,k=1):
    import numpy as np
    best=max([("S001",A),("S002",B)], key=lambda c: float(e@c[1]))
    return [{"student_id":best[0],"name":best[0],"uid":best[0],"similarity":float(e@best[1])}]
def mk():
    out=[]; return Matcher(window=4,cooldown=2,threshold=.5,outcome_sink=out.append,
                           face_search=search,clock=lambda:0.0), out
# accepted
m,o=mk(); m.add_tap("U","S001",A,ts=100); m.on_face({"track_id":1,"embedding":A,"ts":101,"is_live":True}); m.resolve(105)
assert o[0]["status"]==decision.ACCEPTED
# tailgating (face, no tap)
m,o=mk(); m.on_face({"track_id":7,"embedding":B,"ts":100,"is_live":True}); m.resolve(105)
assert o[0]["status"]==decision.TAILGATING and o[0]["uid"]==""
# no_face / spoof
m,o=mk(); m.add_tap("U","S001",A,ts=100); m.resolve(105); assert o[0]["status"]==decision.NO_FACE
m,o=mk(); m.add_tap("U","S001",A,ts=100); m.on_face({"track_id":1,"embedding":A,"ts":101,"is_live":False}); m.resolve(105)
assert o[0]["status"]==decision.SPOOF
print("matcher edge cases OK")
PY
```

Async path end-to-end (perception on, no camera → tap queues then resolves to `no_face`):

```bash
PERCEPTION_ENABLED=true PERCEPTION_SOURCE=/nonexistent.mp4 ASSOC_WINDOW_SEC=1 RESOLVE_INTERVAL_SEC=0.3 \
  $PY -m uvicorn backend.main:app --port 8002 &
sleep 6
curl -s -XPOST localhost:8002/tap -H 'Content-Type: application/json' -d '{"uid":"C3BE343A"}'  # {"status":"queued",...}
sleep 3
curl -s "localhost:8002/api/attendance?student_id=S001&limit=1" | $PY -m json.tool  # status: no_face
kill %1
```
✅ Pass: edge cases assert clean; queued tap async-resolves to `no_face`.

---

## Step 33 (part) — enroll `--capture` fix + shared core

```bash
# Shared core is pure (no camera): feed a synthetic embedding through it.
PYTHONPATH=. $PY - <<'PY'
import numpy as np
from backend import enroll
ref = enroll.average_reference([np.eye(512,dtype=np.float32)[0], np.eye(512,dtype=np.float32)[0]])
assert ref is not None and abs(np.linalg.norm(ref)-1) < 1e-5
print("average_reference OK (unit-normalized)")
PY

# With a webcam + an enrolled student that has consent:
python -m backend.enroll S001 --capture 3      # must NOT crash on the Probe tuple
```
✅ Pass: `average_reference` returns a unit vector; `--capture` runs (needs a camera).

---

## Step 20 — privacy / consent / audit / retention

Consent gate + audit + erasure (uses a throwaway student so it's safe to delete):

```bash
# seed a throwaway student
$PY - <<'PY'
from backend import db
with db.get_conn() as c:
    c.cursor().execute("INSERT INTO students(student_id,uid,name) VALUES('ZTEST','ZZTESTUID','Z') "
                       "ON CONFLICT (student_id) DO NOTHING")
print("seeded ZTEST")
PY

# consent OFF policy -> consent_ok true (back-compat)
FACE_CONSENT_REQUIRED=false PYTHONPATH=. $PY -c "from backend import db,privacy; print('gate off ->', privacy.consent_ok(db.get_student('ZTEST')))"
# consent ON policy -> refused until granted
FACE_CONSENT_REQUIRED=true  PYTHONPATH=. $PY -c "from backend import db,privacy; print('gate on, no consent ->', privacy.consent_ok(db.get_student('ZTEST')))"

# grant consent via API, then read audit
curl -s -XPOST $BASE/api/students/ZTEST/consent -H 'Content-Type: application/json' \
  -H 'X-Operator-Actor: tester' -d '{"granted":true}'
curl -s "$BASE/api/audit?limit=3" | $PY -m json.tool     # shows a 'consent' entry

# retention purge (dry unless the *_RETENTION_DAYS are set)
make purge

# right-to-erasure: deletes logs + roster row + writes audit
curl -s -XDELETE $BASE/api/students/ZTEST -H 'X-Operator-Actor: tester' | $PY -m json.tool
curl -s "$BASE/api/audit?limit=3" | $PY -m json.tool      # shows an 'erase' entry
```
✅ Pass: gate off → allowed; gate on + no consent → refused; consent/erase write audit
rows; `make purge` runs; delete removes the student and logs.

---

## Regression — sync 1:1 flow still works (perception off)

```bash
curl -s -XPOST $BASE/tap -H 'Content-Type: application/json' -d '{"uid":"C3BE343A"}' | $PY -m json.tool
```
✅ Pass: returns a `log` with a status (`unverified` if no camera/face — fail-open).

---

## Deferred (needs hardware)

- **Step 30/31 live**: real webcam + video-file correlation, 3–5 students/s on the RTX 1050.
- **Steps 7/8/9 live**: liveness threshold calibration, real SMTP send, `ENFORCE_2FA=true`.
- **`make up` full image build**: pulls the large CV/scipy dep tree (slow on this network).
