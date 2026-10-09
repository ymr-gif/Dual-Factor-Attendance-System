"""Serial port selection, and the two routes that list cameras and serial ports.

`ports.pick_port` decides which port the reader opens; the CLI (`make ports`) and
GET /api/serial/ports call the same function. The connected devices are faked.
"""

import pytest

from backend import ports

BOARD = {"device": "/dev/ttyUSB0", "likely_board": True}
OTHER = {"device": "/dev/ttyS0", "likely_board": False}


@pytest.fixture
def machine(monkeypatch):
    """A machine whose serial devices are whatever the test says they are."""
    state = {"present": set(), "listed": []}
    monkeypatch.delenv("SERIAL_PORT", raising=False)
    monkeypatch.delenv("SERIAL_PORT_AUTO", raising=False)
    monkeypatch.setattr(ports.os.path, "exists", lambda path: path in state["present"])
    monkeypatch.setattr(ports, "list_ports_detailed", lambda: state["listed"])
    return state


def test_with_nothing_set_the_default_port_is_opened_when_it_exists(machine):
    machine["present"] = {"/dev/ttyACM0"}
    machine["listed"] = [BOARD]

    assert ports.pick_port() == "/dev/ttyACM0"


def test_with_nothing_set_and_no_default_port_the_likely_board_is_opened(machine):
    machine["listed"] = [OTHER, BOARD]

    assert ports.pick_port() == "/dev/ttyUSB0"


def test_nothing_plausible_connected_means_no_port(machine):
    machine["listed"] = [OTHER]

    assert ports.pick_port() is None


def test_a_configured_port_that_is_present_wins_over_a_likely_board(machine, monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/ttyS0")
    machine["present"] = {"/dev/ttyS0"}
    machine["listed"] = [BOARD]

    assert ports.pick_port() == "/dev/ttyS0"


def test_a_configured_port_that_is_missing_falls_back_to_the_likely_board(machine, monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/ttyGONE")
    machine["listed"] = [BOARD]

    assert ports.pick_port() == "/dev/ttyUSB0"


@pytest.mark.parametrize(
    ("configured", "expected"), [("/dev/ttyGONE", "/dev/ttyGONE"), (None, "/dev/ttyACM0")]
)
def test_with_auto_detect_off_only_the_named_port_is_ever_opened(
    machine, monkeypatch, configured, expected
):
    monkeypatch.setenv("SERIAL_PORT_AUTO", "false")
    if configured:
        monkeypatch.setenv("SERIAL_PORT", configured)
    machine["listed"] = [BOARD]

    assert ports.pick_port() == expected


def test_the_reader_and_the_listing_name_the_same_port(machine):
    # The reader passes its own default; the CLI and the API pass nothing.
    machine["present"] = {"/dev/ttyACM0"}
    machine["listed"] = [BOARD]

    assert ports.pick_port(ports.DEFAULT_PORT) == ports.pick_port()


@pytest.mark.parametrize(
    ("path", "keys"),
    [
        ("/api/cameras", {"cameras", "configured", "auto_select", "prefer_external", "in_use"}),
        ("/api/serial/ports", {"ports", "configured", "auto_detect", "would_open"}),
    ],
)
def test_device_listings_need_the_operator_token(client, backend_main, monkeypatch, path, keys):
    monkeypatch.setattr(backend_main, "OPERATOR_TOKEN", "s3cret")
    monkeypatch.setattr(backend_main.cameras, "list_cameras", lambda *a, **k: [])
    monkeypatch.setattr(backend_main.ports, "list_ports_detailed", lambda: [])
    monkeypatch.setattr(backend_main.ports, "pick_port", lambda *a, **k: None)

    assert client.get(path).status_code == 401
    answer = client.get(path, headers={"X-Operator-Token": "s3cret"})
    assert answer.status_code == 200
    assert set(answer.json()) == keys
