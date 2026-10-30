"""Decode the control report forms observed on this VO1060, without guessing pen data."""

from dataclasses import dataclass

BUTTON_CODES = (0x08, 0x04, 0x02, 0x01, 0x10)
CONTROLS = tuple(f"button_{code:02x}" for code in BUTTON_CODES) + ("wheel_01", "wheel_02")


@dataclass(frozen=True)
class ControlEvent:
    control: str
    pressed: bool


class Decoder:
    def __init__(self) -> None:
        self.pressed: set[str] = set()
        self.unverified_button_report = False

    def decode(self, report: bytes) -> ControlEvent | None:
        self.unverified_button_report = False
        if len(report) != 13 or report[:2] != b"\x09\x42":
            return None
        kind, code = report[2], report[4]
        if kind == 1 and (code not in BUTTON_CODES or report[3] not in (0, 1)):
            self.unverified_button_report = True
            return None
        if report[3] not in (0, 1):
            return None
        if kind == 1 and code in BUTTON_CODES:
            control = f"button_{code:02x}"
        elif kind == 3 and code in (1, 2):
            control = f"wheel_{code:02x}"
        else:
            return None
        pressed = bool(report[3])
        if pressed == (control in self.pressed):
            return None
        if pressed:
            self.pressed.add(control)
        else:
            self.pressed.remove(control)
        return ControlEvent(control, pressed)

    def reset(self) -> None:
        self.pressed.clear()
