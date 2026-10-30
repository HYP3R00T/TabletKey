import json
import os
import signal
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tabletkey import daemon, ipc
from tabletkey.config import Settings
from tabletkey.device import Interface
from tabletkey.protocol import ControlEvent


@pytest.fixture
def private_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    yield
    daemon.stop()


def test_detached_start_status_invalid_config_and_graceful_stop(private_environment):
    # A stale socket must not prevent recovery, and no PID file should be trusted.
    endpoint = ipc.runtime_dir() / "daemon.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
        stale.bind(str(endpoint))
    assert not ipc.status()["running"]
    running = daemon.start(no_device=True)
    try:
        assert running["running"]
        assert running["settings"]["output_enabled"]
        assert not running["output_active"]
        assert daemon.start(no_device=True)["pid"] == running["pid"]
        with pytest.raises(ValueError):
            ipc.request("configure", settings={"invalid": True})
        assert ipc.status()["settings"] == Settings().to_dict()
        rejected = subprocess.run(
            [sys.executable, "-m", "tabletkey", "daemon", "run"], capture_output=True, text=True, timeout=8
        )
        assert rejected.returncode == 2
        assert "already running" in rejected.stderr
        assert ipc.status()["pid"] == running["pid"]
    finally:
        daemon.stop()
    assert not ipc.status()["running"]
    assert not endpoint.exists()
    daemon.stop()


def test_sigterm_removes_endpoint_and_allows_restart(private_environment):
    running = daemon.start(no_device=True)
    os.kill(running["pid"], signal.SIGTERM)
    daemon.stop()
    assert not ipc.status()["running"]
    assert daemon.start(no_device=True)["running"]


def test_cli_settings_update_running_daemon(private_environment):
    daemon.start(no_device=True)
    changed = subprocess.run(
        [sys.executable, "-m", "tabletkey", "config", "set", "button_08", "CTRL+Z"],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert changed.returncode == 0, changed.stderr
    assert ipc.status()["settings"]["bindings"]["button_08"] == "CTRL+Z"
    displayed = subprocess.run(
        [sys.executable, "-m", "tabletkey", "daemon", "status", "--json"],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert json.loads(displayed.stdout)["running"]


def test_reconnect_and_stop_release_output(monkeypatch):
    from tabletkey import device

    class Handle:
        def read(self, size):
            return b""

        def close(self):
            pass

    class FakeOutput:
        closed = False

        def close(self):
            self.closed = True

    current = [Interface("/dev/hidraw-a", 2)]
    monkeypatch.setattr(daemon, "load_settings", Settings)
    monkeypatch.setattr(device, "discover", lambda: current)
    monkeypatch.setattr(daemon, "access_problem", lambda: None)
    monkeypatch.setattr(device, "otd_running", lambda: False)
    monkeypatch.setattr(device, "grab_kernel_inputs", lambda: [])
    monkeypatch.setattr(device, "open_standalone_interfaces", lambda items: [(item, Handle()) for item in items])
    worker = daemon.Daemon()
    worker.scan()
    assert worker.snapshot()["connected"]
    worker.decoder.pressed.add("button_08")
    active = FakeOutput()
    monkeypatch.setattr(worker, "output", active)
    current.clear()
    worker.scan()
    assert active.closed
    assert not worker.snapshot()["connected"]
    assert not worker.decoder.pressed
    current.append(Interface("/dev/hidraw-new", 2))
    worker.scan()
    assert worker.snapshot()["interfaces"][0]["path"] == "/dev/hidraw-new"
    worker.disconnect()


def test_reload_releases_output_before_new_mapping(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon()
    released = []

    class FakeOutput:
        def close(self):
            released.append(ControlEvent("button_08", False))

    monkeypatch.setattr(worker, "output", FakeOutput())
    worker.dispatch({"command": "reload"})
    assert released == [ControlEvent("button_08", False)]
    assert worker.output is None


def test_missing_uinput_keeps_daemon_available_for_diagnostics(monkeypatch):
    from evdev.uinput import UInputError

    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon()
    worker.settings.output_enabled = True
    monkeypatch.setattr(worker, "handles", [(Interface("/dev/fake", 2), SimpleNamespace(close=lambda: None))])

    def unavailable(settings):
        raise UInputError("/dev/uinput cannot be opened")

    monkeypatch.setattr(daemon, "Output", unavailable)
    worker.ensure_output()
    assert worker.output_future is not None
    with pytest.raises(UInputError):
        worker.output_future.result(timeout=1)
    worker.ensure_output()
    assert worker.running
    assert not worker.snapshot()["output_active"]
    assert "Standalone output unavailable" in worker.snapshot()["output_error"]
    worker.shutdown()


def test_unverified_combined_report_releases_held_keys(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon()
    closed = []

    class FakeOutput:
        def close(self):
            closed.append(True)

    class Handle:
        def __init__(self):
            self.reports = iter([bytes([9, 0x42, 1, 1, 3] + [0] * 8)])

        def read(self, size):
            return next(self.reports, b"")

    monkeypatch.setattr(worker, "handles", [(Interface("/dev/fake", 2), Handle())])
    monkeypatch.setattr(worker, "output", FakeOutput())
    worker.decoder.pressed.add("button_01")
    worker.poll_input()
    assert closed == [True]
    assert not worker.decoder.pressed
    assert worker.output_error is not None
    assert "held keys released" in worker.output_error
