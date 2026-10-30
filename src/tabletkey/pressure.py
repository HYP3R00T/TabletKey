"""Pressure response shared by settings, pen output, telemetry, and the preview."""

import math
from dataclasses import dataclass
from typing import Self

SENSOR_MAX = 8191


@dataclass(frozen=True)
class PressureSettings:
    full_input: float = 1.0
    gamma: float = 1.0
    deadzone: float = 0.0

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict) or set(value) != {"full_input", "gamma", "deadzone"}:
            raise ValueError("Pressure settings require full_input, gamma, and deadzone")
        if any(type(item) not in (int, float) or not math.isfinite(item) for item in value.values()):
            raise ValueError("Pressure settings must be finite numbers")
        full, gamma, deadzone = value["full_input"], value["gamma"], value["deadzone"]
        if not 0.1 <= full <= 1 or not 0.2 <= gamma <= 3 or not 0 <= deadzone <= 0.2 or deadzone >= full:
            raise ValueError("Pressure requires 10–100% full input, a 0.2–3 curve, and a smaller 0–20% deadzone")
        return cls(float(full), float(gamma), float(deadzone))


def map_pressure(raw: int, settings: PressureSettings) -> int:
    normalized = min(1.0, max(0.0, raw / SENSOR_MAX))
    if normalized <= settings.deadzone:
        return 0
    fraction = min(1.0, (normalized - settings.deadzone) / (settings.full_input - settings.deadzone))
    return round(SENSOR_MAX * fraction**settings.gamma)
