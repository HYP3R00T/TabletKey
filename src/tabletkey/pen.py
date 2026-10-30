"""VO1060 pen reports and native pressure-sensitive Linux tablet output."""

import time
from dataclasses import dataclass
from typing import Any

from evdev import AbsInfo, UInput, ecodes

from tabletkey.displays import Display, apply_routes
from tabletkey.pressure import SENSOR_MAX, PressureSettings, map_pressure
from tabletkey.proximity import PEN_TIMEOUT

MAX_X = 50800
MAX_Y = 31750
MAX_PRESSURE = SENSOR_MAX


@dataclass(frozen=True)
class PenEvent:
    x: int
    y: int
    pressure: int
    barrel1: bool
    barrel2: bool


def reported_pressure(report: bytes) -> int | None:
    if len(report) != 13 or (report[0] != 9 or report[1] not in (0x41, 0x42)) or not report[2] & 0x20:
        return None
    return int.from_bytes(report[9:11], "little")


def decode_pen(report: bytes) -> PenEvent | None:
    pressure = reported_pressure(report)
    if pressure is None:
        return None
    x = int.from_bytes(report[3:6], "little")
    y = int.from_bytes(report[6:9], "little")
    if x > MAX_X or y > MAX_Y or pressure > MAX_PRESSURE:
        return None
    return PenEvent(x, y, pressure, bool(report[2] & 2), bool(report[2] & 4))


def map_point(event: PenEvent, displays: list[Display], area: tuple[float, float, float, float], rotation: int):
    left, top, right, bottom = area
    x = min(1.0, max(0.0, (event.x / MAX_X - left) / (right - left)))
    y = min(1.0, max(0.0, (event.y / MAX_Y - top) / (bottom - top)))
    if rotation == 90:
        x, y = 1 - y, x
    elif rotation == 180:
        x, y = 1 - x, 1 - y
    elif rotation == 270:
        x, y = y, 1 - x
    min_x, min_y = min(item.x for item in displays), min(item.y for item in displays)
    max_x = max(item.x + item.width for item in displays)
    max_y = max(item.y + item.height for item in displays)
    global_x = min_x + x * (max_x - min_x - 1)
    global_y = min_y + y * (max_y - min_y - 1)

    def distance(item):
        dx = max(item.x - global_x, 0, global_x - (item.x + item.width - 1))
        dy = max(item.y - global_y, 0, global_y - (item.y + item.height - 1))
        return dx * dx + dy * dy

    target = min(displays, key=distance)
    local_x = min(1.0, max(0.0, (global_x - target.x) / max(1, target.width - 1)))
    local_y = min(1.0, max(0.0, (global_y - target.y) / max(1, target.height - 1)))
    return target, round(local_x * MAX_X), round(local_y * MAX_Y)


class PenOutput:
    def __init__(
        self, displays: list[Display], target: str, area: tuple, rotation: int, pressure: PressureSettings | None = None
    ) -> None:
        if target == "all":
            self.displays = list(displays)
        elif target == "auto":
            self.displays = displays[:1]
        else:
            self.displays = [item for item in displays if item.name == target]
        if not self.displays:
            raise ValueError(f"Selected display {target!r} is not connected")
        self.area, self.rotation = area, rotation
        self.pressure = pressure or PressureSettings()
        self.devices: dict[str, UInput] = {}
        self.active: UInput | None = None
        self.last_report = 0.0
        apply_routes(self.displays)
        try:
            for display in self.displays:
                capabilities: Any = {
                    ecodes.EV_KEY: [ecodes.BTN_TOOL_PEN, ecodes.BTN_TOUCH, ecodes.BTN_STYLUS, ecodes.BTN_STYLUS2],
                    ecodes.EV_ABS: [
                        (ecodes.ABS_X, AbsInfo(0, 0, MAX_X, 0, 0, 200)),
                        (ecodes.ABS_Y, AbsInfo(0, 0, MAX_Y, 0, 0, 200)),
                        (ecodes.ABS_PRESSURE, AbsInfo(0, 0, MAX_PRESSURE, 0, 0, 0)),
                    ],
                }
                self.devices[display.name] = UInput(
                    capabilities,
                    name=display.pen_name,
                    vendor=0x1,
                    product=0x1060,
                    input_props=[ecodes.INPUT_PROP_DIRECT, ecodes.INPUT_PROP_POINTER],
                )
        except BaseException:
            self.close()
            raise

    def handle(self, event: PenEvent) -> None:
        target, x, y = map_point(event, self.displays, self.area, self.rotation)
        device = self.devices[target.name]
        if self.active is not device:
            self.release()
            self.active = device
        device.write(ecodes.EV_KEY, ecodes.BTN_TOOL_PEN, 1)
        device.write(ecodes.EV_ABS, ecodes.ABS_X, x)
        device.write(ecodes.EV_ABS, ecodes.ABS_Y, y)
        pressure = map_pressure(event.pressure, self.pressure)
        device.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, pressure)
        device.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, int(pressure > 0))
        device.write(ecodes.EV_KEY, ecodes.BTN_STYLUS2, int(event.barrel1))
        device.write(ecodes.EV_KEY, ecodes.BTN_STYLUS, int(event.barrel2))
        device.syn()
        self.last_report = time.monotonic()

    def release(self) -> None:
        device, self.active = self.active, None
        if device is not None:
            device.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, 0)
            for key in (ecodes.BTN_TOUCH, ecodes.BTN_STYLUS, ecodes.BTN_STYLUS2, ecodes.BTN_TOOL_PEN):
                device.write(ecodes.EV_KEY, key, 0)
            device.syn()

    def expire(self) -> None:
        if self.active is not None and time.monotonic() - self.last_report > PEN_TIMEOUT:
            self.release()

    def close(self) -> None:
        try:
            self.release()
        finally:
            for device in self.devices.values():
                device.close()
            self.devices.clear()
