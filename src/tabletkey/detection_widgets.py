"""Live binary proximity and packet timing, separate from pressure response."""

import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DetectionPlot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.history: list[list] = []
        self.setMinimumSize(310, 180)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(105, 20, -18, -35)
        painter.setPen(self.palette().color(self.foregroundRole()))
        for level, label in ((True, "Detected"), (False, "Not detected")):
            y = rect.top() if level else rect.bottom()
            painter.drawText(QRectF(0, y - 10, 95, 20), Qt.AlignmentFlag.AlignRight, label)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        now = time.monotonic()
        start = now - 10
        visible = [sample for sample in self.history if sample[0] >= start]
        previous = [sample for sample in self.history if sample[0] < start]
        # Do not invent a state before the first measured transition.
        if previous:
            visible.insert(0, [start, previous[-1][1], previous[-1][2]])
        if visible:
            path = QPainterPath()
            y = rect.top() if visible[0][1] else rect.bottom()
            x = rect.left() + max(0, (visible[0][0] - start) / 10) * rect.width()
            path.moveTo(x, y)
            for stamp, detected, _ in visible[1:]:
                x = rect.left() + (stamp - start) / 10 * rect.width()
                path.lineTo(x, y)
                y = rect.top() if detected else rect.bottom()
                path.lineTo(x, y)
            path.lineTo(rect.right(), y)
            painter.setPen(QPen(QColor("#16816e"), 3))
            painter.drawPath(path)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(
            QRectF(0, self.height() - 26, self.width(), 22),
            Qt.AlignmentFlag.AlignCenter,
            "Last 10 seconds → now · detection is binary",
        )


class DetectionPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.state = QLabel("Start the driver to inspect pen detection.")
        self.state.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(self.state)
        self.timing = QLabel()
        self.timing.setWordWrap(True)
        layout.addWidget(self.timing)
        self.history = DetectionPlot()
        layout.addWidget(self.history)
        self.events = QLabel()
        self.events.setWordWrap(True)
        layout.addWidget(self.events)
        explanation = QLabel(
            "Hover the pen, then slowly lift it and lower it. The graph shows when reports establish detection "
            "and when the tablet reports a range exit or the driver times out. Counters retain brief drops "
            "that may be too short to see on the graph.\n\n"
            "Height and signal strength: not available in the decoded protocol. Pressure measures contact, "
            "not hover height. Packet gaps measure timing, not signal intensity.\n\n"
            "A range exit releases pen contact immediately. Without a range-exit report, 500 ms of silence "
            "releases the pen as a safety fallback. This cannot extend the tablet's physical reading range."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addStretch()

    def update_status(self, value: dict) -> None:
        detection = value.get("detection")
        if not value.get("running") or detection is None:
            self.state.setText("Start or restart the driver to inspect pen detection.")
            self.timing.clear()
            self.events.clear()
            self.history.history = []
            self.history.update()
            return
        detected = detection["in_range"]
        pressure = (value.get("pen") or {}).get("pressure", 0)
        mode = "Contact" if pressure else "Hovering"
        self.state.setText(f"Detected · {mode}" if detected else "Not detected")
        age = detection["last_report_ms"]
        age_text = "No report yet" if age is None else f"Last pen report: {age:.0f} ms ago"
        output = "in range" if detection["output_in_range"] else "out of range / paused"
        self.timing.setText(
            f"{age_text} · {detection['reports_last_second']} reports in the last second\n"
            f"Largest gap within detection: {detection['max_gap_ms']:.1f} ms · Virtual pen: {output}"
        )
        self.events.setText(
            f"Since driver start: {detection['range_exits']} tablet range exits · "
            f"{detection['timeouts']} report timeouts\nLatest state reason: {detection['reason']}"
        )
        self.history.history = detection["history"]
        self.history.update()
