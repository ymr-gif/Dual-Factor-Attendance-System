# Hardware troubleshooting

Field notes for the two devices the guardpost depends on: the RC522 reader on the
Arduino, and the camera. Both fail *quietly* — the backend fails open by design, so a
dead device shows up as taps logged `unverified` rather than as an error.

---

## Reader: `READY` arrives but no `UID:` lines

**Symptom.** The reader connects and stays connected, but tapping a card logs nothing.
`make ports` shows the board, `reader.launchd.log` shows `listening on /dev/cu.usbmodem… @ 9600`,
and no taps follow.

**Isolate the layer before touching code.** Stop the reader (it owns the port) and watch
the raw serial:

```bash
launchctl unload ~/Library/LaunchAgents/com.nfc-scan.reader.plist   # macOS
.venv/bin/python - <<'PY'
import serial, time
s = serial.Serial('/dev/cu.usbmodem14201', 9600, timeout=1)   # your port from `make ports`
t0 = time.time()
while time.time() - t0 < 45:
    line = s.readline()
    if line:
        print('RAW:', repr(line), flush=True)
s.close()
PY
```

Opening the port resets the board, so the boot lines appear within a second or two. The
sketch self-tests the reader at boot and prints the verdict *before* `READY`:

| Boot line | Meaning |
| --- | --- |
| `RC522:0x91 OK` / `0x92 OK` | Genuine NXP chip, answering consistently |
| `RC522:0xNN OK-CLONE` | Clone chip, but a stable value — fine, most modules are clones |
| `RC522:0xNN UNSTABLE-SPI` | **Reads are noise** — wiring/power, see below |
| `RC522:0x00 NO-COMMS` / `0xFF` | Nothing answering at all — unpowered or disconnected |

Then tap a card:

| Raw output | Meaning |
| --- | --- |
| `b'UID:XXXXXXXX\r\n'` per tap | Board is fine — any fault is in the reader/API path |
| Nothing on tap, but the boot line says `OK`/`OK-CLONE` | Link is sound; suspect the card (non-MIFARE reads as silence) or antenna |
| Nothing on tap, boot line says `UNSTABLE-SPI`/`NO-COMMS` | Fix the link first; card behaviour means nothing until then |
| No boot lines at all | Wrong port, wrong baud, or the sketch is not running |
| Raw `\xff\xff\xff…` | Signal degrading after boot — same wiring/power causes |

### Why the boot check reads the register nine times

`PCD_Init()` only *writes* registers — it never reads one back. It therefore "succeeds" with
the reader unplugged, the sketch prints `READY`, and `loop()` then detects nothing forever.
Silence, no error. That is why a clean `READY` proves nothing about the reader.

`VersionReg` is a hardware constant, so reading it repeatedly doubles as a bus test: a sound
link returns the same value every time. **A plausible-looking value can still be noise.**

**Observed 2026-07-21 on the macOS box**, and the reason this check exists in its current form:

```
first boot:   RC522:0xB2      <- looks like a clone version; actually noise
second boot:  RC522:0x06      <- same constant, different value
third boot:   RC522:0x02
```

A first pass at this check only flagged `0x00`/`0xFF`, so it reported `0xB2` as `OK` and sent
the debugging in the wrong direction — a single lucky `UID:` read on the same marginal bus
reinforced the mistake. Values that vary between reads are the tell, and noise is usually
neither `0x00` nor `0xFF`. Distrust any version outside `0x91`/`0x92` until it repeats.

Earlier in the same session the board emitted a burst of raw `0xFF` bytes on tap. The sketch
only ever emits ASCII, so that was the same fault at a coarser level: an undriven SPI line
reads back as all-ones.

**`MISO` is the prime suspect for all of the above** — it is the only line the chip drives
back to the Arduino, so writes keep appearing to work while every read returns rubbish.

**Checks, cheapest first.** Reset the board after each one and read the boot line — that is
the whole feedback loop. Do not judge by whether taps work; judge by `OK`/`OK-CLONE`.

1. **`MISO` → `12`.** The one line the chip drives. A bad `MISO` produces `UNSTABLE-SPI`
   while everything else looks healthy.
2. **`GND`.** A weak ground floats the reference for every other signal and looks like noise
   on all of them.
3. **Swap the jumper wires themselves.** DuPont wires fail at the crimp while looking perfect.
   Replace the `MISO` and `GND` wires before suspecting the module.
4. **`VCC` must be on `3.3V`, never `5V`.** The most common way to kill an RC522. A
   partly-damaged module reads intermittently, which looks exactly like "worked yesterday,
   dead today".
5. **Power delivery, even when the module's LED is lit.** The Uno's onboard 3.3V regulator
   supplies ~50 mA; an RC522 draws more than that when it energises its RF field. The LED
   lights on far less current than the chip needs to run reliably, so a lit LED does not mean
   the rail is adequate. A sagging rail under load reads as `UNSTABLE-SPI`. If reseating does
   not fix it, feed the module from an external 3.3V supply (common ground with the Uno).
6. **Shorter, firmer wiring.** SPI tolerates long loose breadboard jumpers poorly.
7. **Verify SPI wiring** against the sketch's pin defines:

   | RC522 | Uno |
   | --- | --- |
   | `SDA`/`SS` | `10` (`SS_PIN`) |
   | `SCK` | `13` |
   | `MOSI` | `11` |
   | `MISO` | `12` |
   | `RST` | `9` (`RST_PIN`) |
   | `GND` | `GND` |
   | `VCC` | `3.3V` |

8. **Try another card** — but only once the boot line reads `OK`/`OK-CLONE`.
   `PICC_IsNewCardPresent()` returns false for non-MIFARE cards: silence, not an error.
   Silence on *one* card but not another is a card problem, not a reader problem.

### Reflashing

The reader must be stopped first — it holds the port, and the upload needs it:

```bash
launchctl unload ~/Library/LaunchAgents/com.nfc-scan.reader.plist   # macOS
CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
CFG=~/.arduinoIDE/arduino-cli.yaml
"$CLI" --config-file "$CFG" lib install MFRC522        # once; not preinstalled here
"$CLI" --config-file "$CFG" board list                 # confirm port + FQBN
"$CLI" --config-file "$CFG" compile --fqbn arduino:avr:uno arduino/nfc_scan
"$CLI" --config-file "$CFG" upload -p /dev/cu.usbmodem14201 --fqbn arduino:avr:uno arduino/nfc_scan
launchctl load ~/Library/LaunchAgents/com.nfc-scan.reader.plist
```

arduino-cli ships inside the IDE rather than on `PATH`, hence the full path above. A CH340
clone board reports as `Unknown` (the chip carries no board identity) and needs its FQBN given
explicitly — `arduino:avr:nano:cpu=atmega328old` for most Nano clones.

**Remember to restart the reader** when finished — it stays down until you do:

```bash
launchctl load ~/Library/LaunchAgents/com.nfc-scan.reader.plist
```

---

## Reader: port keeps changing

Not a fault. A board re-enumerates under a different name when moved to another USB socket
(`/dev/cu.usbmodem14101` → `14201`). Leave `SERIAL_PORT` unset and the reader follows it;
see `backend/ports.py`, `make ports`, and the Serial ports panel in Settings.

---

## Camera: preview works in the browser but the dashboard is black

Two different cameras are in play, and only one of them is the backend's:

- **Register page** — the *browser* opens the camera via `getUserMedia`. Browser permission.
- **Dashboard** — the *backend* owns the camera and serves `/stream.mjpeg`. OS permission.

So a working register preview says nothing about whether the backend has a camera.

**Single owner.** Only one process gets the device. A register page holding the camera blocks
the backend, and `cap.read()` then blocks hard enough that the backend needs a restart after
the browser lets go. Close the register tab before expecting the dashboard feed. A second
USB camera removes the conflict entirely.

**macOS: launchd agents get no camera.** TCC grants camera access to a responsible GUI app.
A launchd agent has none, and command-line binaries cannot be added to the Camera pane
manually, so the backend gets no camera when it auto-starts. This is a genuine either/or:

```bash
make dev-cam     # foreground, camera works, no auto-start
make autostart   # launchd, auto-starts at login, camera idle
```

Grant **Terminal** (not python) camera access in System Settings → Privacy & Security → Camera.

**Warm-up.** AVFoundation returns `ok=False` for the first reads while the capture session
starts; `backend/perception.py` discards `CAMERA_WARMUP_FRAMES` before trusting a read and
tolerates transient dropouts. If a camera needs longer, raise `CAMERA_WARMUP_FRAMES`.

---

## Camera: wrong camera selected

Leave `CAMERA_INDEX` unset and the backend prefers an external USB camera over the built-in
one, falling back to built-in when nothing is plugged in. See `backend/cameras.py`,
`make cameras`, and the Cameras panel in Settings. Pin a specific one with `CAMERA_INDEX`,
or set `CAMERA_PREFER_EXTERNAL=false` to always use the built-in camera.
