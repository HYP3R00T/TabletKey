import pytest
from evdev import ecodes

from tabletkey import pen
from tabletkey.displays import Display
from tabletkey.pen import MAX_PRESSURE, MAX_X, MAX_Y, PenEvent, decode_pen, map_point


class VirtualDevice:
    def __init__(self, capabilities, **attributes):
        self.capabilities = capabilities
        self.attributes = attributes
        self.events = []
        self.closed = False

    def write(self, *event):
        self.events.append(event)

    def syn(self):
        pass

    def close(self):
        self.closed = True


def sample(x=12345, y=23456, pressure=4096, flags=0xA6):
    return (
        bytes([9, 0x41, flags])
        + x.to_bytes(3, "little")
        + y.to_bytes(3, "little")
        + pressure.to_bytes(2, "little")
        + bytes(2)
    )


def test_pen_coordinates_pressure_and_barrel_buttons():
    assert decode_pen(sample()) == PenEvent(12345, 23456, 4096, True, True)
    for data in (sample(x=MAX_X + 1), sample(pressure=MAX_PRESSURE + 1), bytes(13), sample()[:8]):
        assert decode_pen(data) is None


def test_two_monitor_routing_crop_rotation_and_gaps():
    screens = [Display("left", -1920, 0, 1920, 1080), Display("right", 0, 0, 1920, 1080)]
    left, x, _ = map_point(PenEvent(0, 0, 0, False, False), screens, (0, 0, 1, 1), 0)
    assert left.name == "left" and x == 0
    right, x, y = map_point(PenEvent(MAX_X, MAX_Y, 0, False, False), screens, (0, 0, 1, 1), 0)
    assert right.name == "right" and (x, y) == (MAX_X, MAX_Y)
    rotated, x, y = map_point(PenEvent(0, 0, 0, False, False), screens[:1], (0, 0, 1, 1), 90)
    assert (x, y) == (MAX_X, 0)
    _, x, _ = map_point(PenEvent(MAX_X // 4, 0, 0, False, False), screens[:1], (0.25, 0, 0.75, 1), 0)
    assert x == 0


def test_pressure_touch_monitor_crossing_and_shutdown(monkeypatch):
    monkeypatch.setattr(pen, "UInput", VirtualDevice)
    routes = []
    monkeypatch.setattr(pen, "apply_routes", lambda screens: routes.extend(screens))
    screens = [Display("left", 0, 0, 1920, 1080), Display("right", 1920, 0, 1920, 1080)]
    output = pen.PenOutput(screens, "all", (0, 0, 1, 1), 0)
    output.handle(PenEvent(0, 0, 1000, True, False))
    first = output.devices["left"]
    assert (ecodes.EV_ABS, ecodes.ABS_PRESSURE, 1000) in first.events
    assert (ecodes.EV_KEY, ecodes.BTN_TOUCH, 1) in first.events
    output.handle(PenEvent(MAX_X, MAX_Y, 0, False, False))
    assert (ecodes.EV_KEY, ecodes.BTN_TOOL_PEN, 0) in first.events
    devices = list(output.devices.values())
    output.close()
    assert all(item.closed for item in devices)
    assert len(routes) == 2


def test_invalid_monitor_does_not_write_compositor_config(monkeypatch):
    monkeypatch.setattr(pen, "apply_routes", lambda _: pytest.fail("must validate target before writing"))
    with pytest.raises(ValueError):
        pen.PenOutput([Display("main", 0, 0, 1920, 1080)], "missing", (0, 0, 1, 1), 0)
