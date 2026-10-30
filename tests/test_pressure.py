import json
import time
from types import SimpleNamespace

import pytest
from evdev import ecodes

from tabletkey import daemon, pen
from tabletkey.config import Settings
from tabletkey.device import Interface
from tabletkey.displays import Display
from tabletkey.pressure import SENSOR_MAX, PressureSettings, map_pressure


def frame(raw):
    return (
        bytes([9, 0x41, 0xA0])
        + (20000).to_bytes(3, "little")
        + (10000).to_bytes(3, "little")
        + raw.to_bytes(2, "little")
        + bytes(2)
    )


def test_default_is_identity_and_light_touch_reaches_full_at_comfortable_limit():
    for raw in (0, 1, 100, 2048, 4096, SENSOR_MAX):
        assert map_pressure(raw, PressureSettings()) == raw
    soft = PressureSettings(0.65, 0.7)
    assert 0.94 < map_pressure(round(0.6 * SENSOR_MAX), soft) / SENSOR_MAX < 0.96
    assert map_pressure(round(0.65 * SENSOR_MAX), soft) == SENSOR_MAX
    assert map_pressure(0, soft) == 0


def test_curves_are_monotonic_bounded_and_deadzone_stays_zero():
    for gamma in (0.2, 0.7, 1, 1.5, 3):
        settings = PressureSettings(0.7, gamma, 0.02)
        values = [map_pressure(raw, settings) for raw in range(0, SENSOR_MAX + 1, 19)]
        assert values == sorted(values)
        assert min(values) >= 0 and max(values) <= SENSOR_MAX
        assert map_pressure(100, settings) == 0
        assert map_pressure(SENSOR_MAX, settings) == SENSOR_MAX


@pytest.mark.parametrize("field,value", [("full_input", 0), ("gamma", 0), ("gamma", float("nan")), ("deadzone", 0.9)])
def test_invalid_pressure_settings_are_rejected(field, value):
    data = {"full_input": 1, "gamma": 1, "deadzone": 0}
    data[field] = value
    with pytest.raises(ValueError):
        PressureSettings.from_dict(data)


def test_version_two_migrates_to_linear_without_changing_other_pen_settings():
    old = Settings().to_dict()
    old["version"] = 2
    old["pen"].pop("pressure")
    old["pen"].update(display="all", rotation=90, area=[0.1, 0.2, 0.8, 0.9])
    result = Settings.from_dict(old)
    assert result.version == 3 and result.pen.pressure == PressureSettings()
    assert result.pen.display == "all" and result.pen.rotation == 90
    assert result.pen.area == (0.1, 0.2, 0.8, 0.9)


def test_real_pen_output_uses_response_and_touch_respects_deadzone(monkeypatch):
    class Virtual:
        def __init__(self, *args, **kwargs):
            self.events = []

        def write(self, *event):
            self.events.append(event)

        def syn(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(pen, "UInput", Virtual)
    monkeypatch.setattr(pen, "apply_routes", lambda _: None)
    target = pen.PenOutput(
        [Display("main", 0, 0, 1920, 1080)], "auto", (0, 0, 1, 1), 0, PressureSettings(0.65, 0.7, 0.02)
    )
    device = target.devices["main"]
    target.handle(pen.PenEvent(100, 100, 100, False, False))
    assert (ecodes.EV_ABS, ecodes.ABS_PRESSURE, 0) in device.events
    assert (ecodes.EV_KEY, ecodes.BTN_TOUCH, 0) in device.events
    target.handle(pen.PenEvent(100, 100, 6000, False, False))
    assert (ecodes.EV_ABS, ecodes.ABS_PRESSURE, SENSOR_MAX) in device.events
    assert (ecodes.EV_KEY, ecodes.BTN_TOUCH, 1) in device.events
    target.close()


def test_telemetry_preserves_short_peaks_and_raw_values(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon(no_device=True)
    worker.settings.pen.pressure = PressureSettings(0.65, 0.7)
    reports = iter([frame(raw) for raw in (0, 100, 5324, 0)])
    handle = SimpleNamespace(read=lambda size: next(reports, b""), close=lambda: None)
    monkeypatch.setattr(worker, "handles", [(Interface("/dev/fake", 2), handle)])
    worker.poll_input()
    assert [sample[2] for sample in worker.pressure_history] == [0, 100, 5324, 0]
    assert worker.pressure_history[-2][3] == SENSOR_MAX
    assert worker.pressure_max_seen == 5324 and worker.pressure_out_of_range == 0
    worker.shutdown()


def test_idle_pen_clears_stale_pressure_once(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon(no_device=True)
    worker.pen_state = {"x": 100, "y": 100, "pressure": 5000, "mapped_pressure": 5000, "in_range": True}
    worker.last_pen_time = time.monotonic() - 1
    worker.poll_input()
    assert worker.pen_state["pressure"] == 0 and not worker.pen_state["in_range"]
    assert worker.pressure_history[-1][2:] == [0, 0]
    before = len(worker.pressure_history)
    worker.poll_input()
    assert len(worker.pressure_history) == before
    worker.shutdown()


def test_pressure_payload_is_bounded_and_bad_range_is_observable(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon(no_device=True)
    for _ in range(1000):
        worker.add_pressure_sample(5000, 7000)
    assert len(worker.pressure_history) == 600
    for index in range(64):
        worker.events.append({"sequence": index, "control": "button_01", "pressed": True, "time": time.time()})
    assert len(json.dumps(worker.snapshot()).encode()) < 65536
    reports = iter([frame(12000)])
    monkeypatch.setattr(
        worker,
        "handles",
        [(Interface("/dev/fake", 2), SimpleNamespace(read=lambda _: next(reports, b""), close=lambda: None))],
    )
    worker.poll_input()
    assert worker.pressure_max_seen == 12000 and worker.pressure_out_of_range == 1
    assert worker.pen_reports == 0
    worker.shutdown()
