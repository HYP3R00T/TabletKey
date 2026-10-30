import pytest
from evdev import ecodes

from tabletkey import output
from tabletkey.config import Settings
from tabletkey.protocol import ControlEvent


class VirtualDevice:
    def __init__(self, *args, **kwargs):
        self.events = []
        self.closed = False

    def write(self, *event):
        self.events.append(event)

    def syn(self):
        pass

    def close(self):
        self.closed = True


def test_chords_hold_shared_modifiers_until_last_button_releases(monkeypatch):
    monkeypatch.setattr(output, "UInput", VirtualDevice)
    settings = Settings()
    settings.bindings.update(button_01="CTRL+Z", button_02="CTRL+C")
    target = output.Output(settings)
    for event in (
        ControlEvent("button_01", True),
        ControlEvent("button_02", True),
        ControlEvent("button_01", False),
    ):
        target.handle(event)
    ctrl = ecodes.KEY_LEFTCTRL
    assert (ecodes.EV_KEY, ctrl, 0) not in target.keyboard.events
    target.handle(ControlEvent("button_02", False))
    assert target.keyboard.events.count((ecodes.EV_KEY, ctrl, 1)) == 1
    assert target.keyboard.events.count((ecodes.EV_KEY, ctrl, 0)) == 1
    assert not target.held
    target.close()


def test_wheel_emits_once_and_shutdown_releases_held_keys(monkeypatch):
    monkeypatch.setattr(output, "UInput", VirtualDevice)
    settings = Settings()
    settings.bindings.update(wheel_01="SCROLL_UP", button_01="SHIFT+A")
    target = output.Output(settings)
    target.handle(ControlEvent("wheel_01", True))
    target.handle(ControlEvent("wheel_01", False))
    assert target.mouse.events == [(ecodes.EV_REL, ecodes.REL_WHEEL, 1)]
    target.handle(ControlEvent("button_01", True))
    target.close()
    assert target.keyboard.events[-2:] == [(ecodes.EV_KEY, ecodes.KEY_A, 0), (ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)]
    assert target.keyboard.closed and target.mouse.closed


def test_second_virtual_device_failure_closes_first(monkeypatch):
    first = VirtualDevice()
    calls = []

    def create(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise OSError("uinput failure")
        return first

    monkeypatch.setattr(output, "UInput", create)
    with pytest.raises(OSError):
        output.Output(Settings())
    assert first.closed
