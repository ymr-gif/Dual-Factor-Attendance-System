# Pilot on the Acer Nitro 5 (Windows 11): bring-up (18 Nov 2026)

For the Claude CLI on the Nitro 5. Read `docs/pilot-macbook.md` first: its context,
rules, checks (section 4), tests T1 to T10 (section 5), findings outline (section 6),
pre-pilot cleanup (section 7) and Live Feed glossary hold here too. This file only
covers what differs on Windows. Code at `5aad152` or later.

Machine (18 Nov): Nitro 5 board out of its case, Windows 11, 16 GB RAM, Intel UHD plus
an NVIDIA GeForce (GTX 1050 per the paper). An old version of this repo ran here once.

## Rules (same as the MacBook file, plus)

- Never print `.env` (`type`, `Get-Content` with values, `cat`). Check a value by length.
- Do not commit anything Windows-only that breaks Linux or macOS. Doc and script
  additions are fine; code changes need Cabucos's yes and a passing test run.

## Windows traps

| Trap | Why | Fix |
|---|---|---|
| `.env` not read | The backend reads only the process environment; `make` and bash load `.env` on Linux and macOS. Windows has neither | Load it in PowerShell first (below) |
| No `make` | Makefile targets are bash | Run the Python commands directly (below) |
| Camera not auto-picked | Auto-pick globs `/dev/video*` | `python -m backend.cameras`, then set `CAMERA_INDEX` |
| Reader port | Auto-detect uses pyserial's port list, which works on Windows | If not found: `python -m backend.ports`, then `SERIAL_PORT=COM3` (the one listed) |
| Unicode in logs | Logs print `—` and `→`; a redirected Windows console may use cp1252 | Set `PYTHONUTF8=1` (below) |
| insightface install | No Windows wheel; it compiles | Needs the Visual C++ Build Tools. The old install worked, so they are likely present |
| Postgres + pgvector | Runs in Docker | Docker Desktop (WSL2). `docker compose up -d db` |

## 1. Update

```powershell
git pull                                   # 5aad152 or later
py -3.11 -m venv .venv                     # skip if .venv exists
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend; npm ci; npm run build; cd ..
docker compose up -d db                    # pgvector/pgvector:pg16 on port 5433
```

The database on this machine is new or old: the schema updates itself at backend
start. Students enrolled on another machine are not here; enroll on the machine used
for the pilot.

## 2. `.env`

Copy `.env.example` to `.env` if missing. Cabucos types the secrets. Lines to set, as in
`pilot-macbook.md` section 2, plus:

```
CAMERA_INDEX=0          # from python -m backend.cameras; the A4tech, not a built-in one
CAMERA_WIDTH=1280       # try 1280x720 first; drop to 640x480 if under 8 fps
CAMERA_HEIGHT=720
PERCEPTION_ENABLED=true
USE_GPU=false           # CPU first; see section 5
```

Check secrets by length only:

```powershell
(Select-String -Path .env -Pattern '^SMTP_PASSWORD=(.*)$').Matches.Groups[1].Value.Length   # expect 16
```

## 3. Load `.env` and start

In every new PowerShell window, from the repo root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
Get-Content .env | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object {
  $k, $v = $_ -split '=', 2
  $v = ($v -replace '\s+#.*$', '').Trim().Trim('"')
  [Environment]::SetEnvironmentVariable($k.Trim(), $v, 'Process')
}
```

This prints nothing. Then, window 1:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Window 2 (load `.env` the same way first):

```powershell
python -u -m backend.serial_reader
```

Health: `curl.exe -s localhost:8001/health` gives `"status":"ok","db":true`.
Dashboard: `http://localhost:8001/app/`.

## 4. Tests

`python -m pytest tests -q` (497 passed, 11 skipped on Linux, 18 Nov; report any
Windows-only failure with its output). Then `pilot-macbook.md` sections 4 and 5
(T1 to T10, liveness calibration). Write the findings to
`docs/findings-2026-11-18-nitro.md` with the same outline.

Speed target: the `[perception]` line at 8 fps or more, lag not growing over 10 minutes,
tap to verdict about 4 s.

## 5. GPU (only after T1 to T10 pass, and only if there is time)

The code uses the GPU only through CUDA (`backend/face.py`, `gpu_runtime`), with an
automatic CPU fallback.

1. `pip uninstall -y onnxruntime` then `pip install onnxruntime-gpu`.
2. CUDA 12 and cuDNN 9 runtimes must be installed for that onnxruntime-gpu build.
3. `USE_GPU=true` in `.env`, reload `.env`, restart the backend.
4. If the log says `USE_GPU=true but CUDAExecutionProvider unavailable — using CPU`, it
   runs on the CPU as before: nothing breaks. Compare the `[perception]` lines.

If it does not work within 30 minutes, go back: `pip uninstall -y onnxruntime-gpu`,
`pip install onnxruntime`, `USE_GPU=false`. The pilot does not need the GPU.

## 6. Carrying the board

Box with padding, nothing metal touching the board, fans clear, its own power brick.
Bring a monitor, keyboard and mouse. Pack the desktop setup as the fallback if the board
fails at the site.
