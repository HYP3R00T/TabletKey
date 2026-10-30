"""Validated global mappings, saved atomically without needing a running daemon."""

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Self

from evdev import ecodes

from tabletkey.pressure import PressureSettings
from tabletkey.protocol import CONTROLS

ALIASES = {"CTRL": "LEFTCTRL", "ALT": "LEFTALT", "SHIFT": "LEFTSHIFT", "SUPER": "LEFTMETA"}


@dataclass(frozen=True)
class Action:
    keys: tuple[int, ...] = ()
    scroll: int = 0


def parse_binding(binding: str) -> Action:
    value = binding.strip().upper()
    if value in ("", "NONE"):
        return Action()
    if value in ("SCROLL_UP", "SCROLL_DOWN"):
        return Action(scroll=1 if value == "SCROLL_UP" else -1)
    keys = []
    for part in value.split("+"):
        name = ALIASES.get(part.strip(), part.strip())
        name = name if name.startswith("KEY_") else f"KEY_{name}"
        code = ecodes.ecodes.get(name)
        if not isinstance(code, int) or not 1 <= code < ecodes.BTN_MISC:
            raise ValueError(f"Unknown keyboard key: {part!r}. Use e.g. CTRL+Z, ALT+TAB, F5, or SCROLL_UP.")
        if code in keys:
            raise ValueError(f"Duplicate key in shortcut: {part!r}")
        keys.append(code)
    return Action(keys=tuple(keys))


@dataclass
class PenSettings:
    enabled: bool = True
    display: str = "auto"
    area: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    rotation: int = 0
    pressure: PressureSettings = field(default_factory=PressureSettings)

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict) or set(value) not in (
            {"enabled", "display", "area", "rotation"},
            {"enabled", "display", "area", "rotation", "pressure"},
        ):
            raise ValueError("Pen settings require enabled, display, area, and rotation")
        if type(value["enabled"]) is not bool or not isinstance(value["display"], str) or not value["display"].strip():
            raise ValueError("Invalid pen enable flag or display name")
        if type(value["rotation"]) is not int or value["rotation"] not in (0, 90, 180, 270):
            raise ValueError("Pen rotation must be 0, 90, 180, or 270")
        area = value["area"]
        if not isinstance(area, (list, tuple)) or len(area) != 4:
            raise ValueError("Pen area requires normalized left, top, right, bottom values")
        if any(type(item) not in (int, float) or not math.isfinite(item) or not 0 <= item <= 1 for item in area):
            raise ValueError("Pen area values must be finite numbers between 0 and 1")
        if area[0] >= area[2] or area[1] >= area[3]:
            raise ValueError("Pen area must have positive width and height")
        return cls(
            value["enabled"],
            value["display"],
            (float(area[0]), float(area[1]), float(area[2]), float(area[3])),
            value["rotation"],
            PressureSettings.from_dict(value["pressure"]) if "pressure" in value else PressureSettings(),
        )


def default_bindings() -> dict[str, str]:
    values = dict.fromkeys(CONTROLS, "NONE")
    values.update(wheel_01="SCROLL_UP", wheel_02="SCROLL_DOWN")
    return values


@dataclass
class Settings:
    version: int = 3
    output_enabled: bool = True
    bindings: dict[str, str] = field(default_factory=default_bindings)
    pen: PenSettings = field(default_factory=PenSettings)

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict):
            raise ValueError("Settings must be an object")
        version = value.get("version")
        expected = {"version", "output_enabled", "bindings"} | ({"pen"} if version in (2, 3) else set())
        if type(version) is not int or version not in (1, 2, 3) or set(value) != expected:
            raise ValueError("Unsupported settings version or fields")
        if type(value["output_enabled"]) is not bool:
            raise ValueError("Invalid output_enabled flag")
        bindings = value["bindings"]
        if not isinstance(bindings, dict) or set(bindings) != set(CONTROLS):
            raise ValueError("Settings must specify exactly the five button codes and two wheel codes.")
        for binding in bindings.values():
            if not isinstance(binding, str):
                raise ValueError("Bindings must be strings.")
            parse_binding(binding)
        pen = PenSettings.from_dict(value["pen"]) if version in (2, 3) else PenSettings()
        if version == 3 and "pressure" not in value["pen"]:
            raise ValueError("Version-3 pen settings require a pressure response")
        return cls(output_enabled=value["output_enabled"], bindings=dict(bindings), pen=pen)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["pen"]["area"] = list(self.pen.area)
        return result


def config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "tabletkey" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_path()
    if not path.exists():
        return Settings()
    return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_settings(settings: Settings, path: Path | None = None) -> None:
    Settings.from_dict(settings.to_dict())
    path = path or config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(settings.to_dict(), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
