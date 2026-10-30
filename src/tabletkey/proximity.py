"""Packet-based pen detection; no claim of measured height or radio strength."""

import time
from collections import deque

PEN_TIMEOUT = 0.5


def is_range_exit(report: bytes) -> bool:
    # Confirmed in the local hover capture; shared with upstream's VEIKK V1 parser.
    return len(report) == 13 and report[:3] == b"\x09\x41\xc0"


class Detection:
    def __init__(self) -> None:
        self.in_range = False
        self.last_report: float | None = None
        self.max_gap = 0.0
        self.exits = 0
        self.timeouts = 0
        self.reason = "No pen report yet"
        self.history: deque[list] = deque(maxlen=128)
        self.recent: deque[float] = deque(maxlen=512)

    def received(self, now: float) -> None:
        if self.in_range and self.last_report is not None:
            self.max_gap = max(self.max_gap, now - self.last_report)
        self.last_report = now
        self.recent.append(now)
        if not self.in_range:
            self.history.append([now, True, "Pen report"])
        self.in_range = True
        self.reason = "Pen report"

    def lost(self, now: float, reason: str) -> None:
        if reason == "Tablet range exit":
            self.exits += 1
        elif reason == "Report timeout" and self.in_range:
            self.timeouts += 1
        if self.in_range:
            self.history.append([now, False, reason])
        self.in_range = False
        self.reason = reason

    def snapshot(self) -> dict:
        now = time.monotonic()
        return {
            "in_range": self.in_range,
            "last_report_ms": None if self.last_report is None else max(0, (now - self.last_report) * 1000),
            "reports_last_second": sum(now - stamp <= 1 for stamp in self.recent),
            "max_gap_ms": self.max_gap * 1000,
            "range_exits": self.exits,
            "timeouts": self.timeouts,
            "reason": self.reason,
            "history": list(self.history),
            "timeout_ms": PEN_TIMEOUT * 1000,
        }
