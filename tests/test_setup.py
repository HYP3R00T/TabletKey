import pytest

from tabletkey import daemon, setup
from tabletkey.device import Interface


def test_installer_targets_only_tablet_nodes_and_uinput(monkeypatch):
    calls = []
    monkeypatch.setattr(setup.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(setup, "discover", lambda: [Interface("/dev/hidraw8", 2)])
    monkeypatch.setattr(setup, "physical_input_paths", lambda: [])
    monkeypatch.setattr(setup.subprocess, "run", lambda command, **kwargs: calls.append(command))
    setup.install_rules()
    assert calls[0][:5] == ["sudo", "install", "-D", "-m", "0644"]
    assert calls[0][-1] == "/etc/udev/rules.d/70-tabletkey.rules"
    assert ["sudo", "modprobe", "uinput"] in calls
    assert any(command[-1] == "/etc/modules-load.d/tabletkey.conf" for command in calls)
    trigger = next(command for command in calls if "trigger" in command)
    assert "/sys/class/hidraw/hidraw8" in trigger
    assert not any("usermod" in command or "chmod" in command for command in calls)
    text = setup.rule_text()
    assert 'ATTRS{idVendor}=="2feb"' in text and 'ATTRS{idProduct}=="000b"' in text
    assert 'KERNEL=="uinput"' in text


def test_missing_permissions_prevent_pausing_working_otd(monkeypatch):
    monkeypatch.setattr(daemon, "access_problem", lambda: "Run setup")
    monkeypatch.setattr(daemon.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("must not stop OTD"))
    with pytest.raises(OSError, match="Run setup"):
        daemon.pause_otd()


def test_otd_conflict_prevents_initialization(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", daemon.Settings)
    monkeypatch.setattr(daemon, "access_problem", lambda: None)
    monkeypatch.setattr(daemon.device, "otd_running", lambda: True)
    monkeypatch.setattr(
        daemon.device, "open_standalone_interfaces", lambda _: pytest.fail("must not initialize concurrently")
    )
    worker = daemon.Daemon()
    worker.scan()
    assert not worker.initialized
    assert worker.device_error is not None
    assert "OpenTabletDriver is running" in worker.device_error
    worker.shutdown()
