"""Serial port discovery and selection.

The reader's port is not stable: a board re-enumerates under a different name when
moved to another USB socket (/dev/cu.usbmodem14101 -> 14201 on macOS), so pinning
SERIAL_PORT to a literal path breaks on the next replug. This module finds the
board instead of trusting a path.

Two enumeration sources are merged, because neither is complete on its own:
pyserial's comports() carries USB metadata (vid/pid/manufacturer) but on macOS it
sometimes omits usbmodem devices entirely, while globbing /dev finds those devices
but tells us nothing about them.

Env:
  SERIAL_PORT       explicit device path; used as-is when present (auto-detect off)
  SERIAL_PORT_AUTO  false -> never auto-detect, only ever use SERIAL_PORT

CLI:
  python -m backend.ports          list what is connected, best candidate first
"""

import glob
import os

from serial.tools import list_ports

# USB vendor IDs of the boards/adapters this project is likely to be wired to.
KNOWN_VENDORS = {
    0x2341: "Arduino",
    0x2A03: "Arduino (.org)",
    0x1A86: "CH340/CH341",
    0x0403: "FTDI",
    0x10C4: "Silicon Labs CP210x",
    0x16C0: "Teensy/Arduino clone",
    0x239A: "Adafruit",
}

DEVICE_GLOBS = ("/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/ttyACM*", "/dev/ttyUSB*")

# Bluetooth RFCOMM devices show up as serial ports but are never the reader.
_EXCLUDE_MARKERS = ("bluetooth", "-incoming-port")


def _is_excluded(device: str) -> bool:
    d = device.lower()
    return any(m in d for m in _EXCLUDE_MARKERS)


def _looks_like_board(device: str) -> bool:
    d = device.lower()
    return any(k in d for k in ("usbmodem", "usbserial", "ttyacm", "ttyusb"))


def _score(entry: dict) -> int:
    """Higher is a more likely reader board."""
    if entry["vid"] in KNOWN_VENDORS:
        return 100
    if _looks_like_board(entry["device"]):
        return 50
    if entry["vid"] is not None:  # some USB serial device, just not one we know
        return 25
    return 0


def list_ports_detailed() -> list:
    """Every plausible serial port, best candidate first.

    Bluetooth ports are filtered out; a port present in both enumeration sources is
    reported once, keeping whichever entry carries USB metadata.
    """
    found = {}

    for p in list_ports.comports():
        if _is_excluded(p.device):
            continue
        found[p.device] = {
            "device": p.device,
            "description": None if p.description in (None, "n/a") else p.description,
            "manufacturer": p.manufacturer,
            "product": p.product,
            "vid": p.vid,
            "pid": p.pid,
            "vendor_name": KNOWN_VENDORS.get(p.vid),
        }

    for pattern in DEVICE_GLOBS:
        for device in glob.glob(pattern):
            if device in found or _is_excluded(device):
                continue
            found[device] = {
                "device": device,
                "description": None,
                "manufacturer": None,
                "product": None,
                "vid": None,
                "pid": None,
                "vendor_name": None,
            }

    entries = list(found.values())
    for e in entries:
        e["score"] = _score(e)
        e["likely_board"] = e["score"] >= 50
    entries.sort(key=lambda e: (-e["score"], e["device"]))
    return entries


def configured_port():
    """The explicitly configured port, or None when unset/blank."""
    return os.environ.get("SERIAL_PORT") or None


def auto_enabled() -> bool:
    return os.environ.get("SERIAL_PORT_AUTO", "true").strip().lower() not in ("false", "0", "no")


def pick_port(prefer: str | None = None):
    """Resolve the port to open, or None when nothing plausible is connected.

    An explicitly configured port wins whenever it is actually present. Otherwise —
    and only when auto-detect is enabled — the highest-scoring connected board is
    used, so a replug under a new name recovers on the next reconnect.
    """
    prefer = prefer or configured_port()
    if prefer and os.path.exists(prefer):
        return prefer
    if not auto_enabled():
        return prefer
    for entry in list_ports_detailed():
        if entry["likely_board"]:
            return entry["device"]
    return None


def describe(entry: dict) -> str:
    bits = []
    if entry.get("vendor_name"):
        bits.append(entry["vendor_name"])
    elif entry.get("manufacturer"):
        bits.append(entry["manufacturer"])
    if entry.get("product"):
        bits.append(entry["product"])
    elif entry.get("description"):
        bits.append(entry["description"])
    if entry.get("vid") is not None:
        bits.append(f"{entry['vid']:04x}:{entry['pid'] or 0:04x}")
    return "  ".join(bits) or "no USB metadata"


def main():
    entries = list_ports_detailed()
    configured = configured_port()
    chosen = pick_port()

    if not entries:
        print("no serial ports found — is the board plugged in?")
    else:
        print(f"{len(entries)} serial port(s):\n")
        for e in entries:
            mark = "*" if e["device"] == chosen else " "
            flag = "likely board" if e["likely_board"] else "unlikely"
            print(f" {mark} {e['device']}")
            print(f"     {flag}  —  {describe(e)}")
        print("\n * = the port the reader would open")

    print()
    print(f"SERIAL_PORT      {configured or '(unset)'}")
    print(f"auto-detect      {'on' if auto_enabled() else 'off (SERIAL_PORT_AUTO=false)'}")
    print(f"would open       {chosen or '(nothing found)'}")
    if configured and not os.path.exists(configured):
        print(f"\nnote: SERIAL_PORT={configured} is not connected right now.")
        if not auto_enabled():
            print("      auto-detect is off, so the reader will keep waiting for it.")
        elif chosen:
            print(f"      auto-detect falls back to {chosen}.")
        else:
            print("      auto-detect found no board either — plug one in.")
    print("\nTo pin a specific port, set SERIAL_PORT in .env, then restart the reader:")
    print("  launchctl unload ~/Library/LaunchAgents/com.nfc-scan.reader.plist && \\")
    print("  launchctl load   ~/Library/LaunchAgents/com.nfc-scan.reader.plist")


if __name__ == "__main__":
    main()
