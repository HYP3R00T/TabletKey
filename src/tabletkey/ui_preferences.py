"""Display names and learned wheel orientation belong to the UI, not the driver protocol."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tabletkey.config import config_path
from tabletkey.protocol import CONTROLS

DEFAULT_KEY_ORDER = ("button_01", "button_02", "button_04", "button_08")

DEFAULT_NAMES = {
    **{control: f"Key {index}" for index, control in enumerate(DEFAULT_KEY_ORDER, 1)},
    "button_10": "Dial press",
    "wheel_01": "Wheel direction A",
    "wheel_02": "Wheel direction B",
}


@dataclass
class UiPreferences:
    names: dict[str, str] = field(default_factory=dict)
    wheel_clockwise: str | None = None
    key_order: list[str] = field(default_factory=lambda: list(DEFAULT_KEY_ORDER))

    def name(self, control: str) -> str:
        if self.names.get(control):
            return self.names[control]
        if control in self.key_order:
            return f"Key {self.key_order.index(control) + 1}"
        if control.startswith("wheel_") and self.wheel_clockwise:
            return "Wheel clockwise" if control == self.wheel_clockwise else "Wheel counterclockwise"
        return DEFAULT_NAMES[control]

    @classmethod
    def load(cls):
        path = config_path().with_name("interface.json")
        if not path.exists():
            return cls()
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) not in (
            {"names", "wheel_clockwise"},
            {"names", "wheel_clockwise", "key_order"},
        ):
            raise ValueError("Invalid interface preferences")
        names = value["names"]
        if not isinstance(names, dict) or any(
            key not in CONTROLS or not isinstance(name, str) or len(name) > 40 for key, name in names.items()
        ):
            raise ValueError("Invalid control names")
        if value["wheel_clockwise"] not in (None, "wheel_01", "wheel_02"):
            raise ValueError("Invalid learned wheel direction")
        order = value.get("key_order", cls().key_order)
        if not isinstance(order, list) or len(order) != 4 or set(order) != set(cls().key_order):
            raise ValueError("Invalid physical key order")
        return cls(dict(names), value["wheel_clockwise"], list(order))

    def save(self) -> None:
        path = config_path().with_name("interface.json")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".interface-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(asdict(self), stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
