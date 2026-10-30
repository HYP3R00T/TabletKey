"""Live pressure history and editable response preview, without altering sensor values."""

import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from tabletkey.pressure import SENSOR_MAX, PressureSettings, map_pressure


class PressurePlot(QWidget):
    def __init__(self, curve: bool = False) -> None:
        super().__init__()
        self.curve = curve
        self.settings = PressureSettings()
        self.samples: deque[list] = deque(maxlen=3200)
        self.current_raw = 0
        self.setMinimumSize(310, 155)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(42, 12, -14, -30)
        text = self.palette().color(self.foregroundRole())
        for level in (0, 0.5, 1):
            y = rect.bottom() - level * rect.height()
            painter.setPen(QPen(QColor(140, 150, 160, 65), 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(text)
            painter.drawText(QRectF(0, y - 9, 36, 18), Qt.AlignmentFlag.AlignRight, f"{level * 100:.0f}%")
        if self.curve:
            painter.setPen(QPen(QColor("#89939f"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(rect.bottomLeft(), rect.topRight())
            points = [
                (x / 100, map_pressure(round(x / 100 * SENSOR_MAX), self.settings) / SENSOR_MAX) for x in range(101)
            ]
            self.draw_trace(painter, rect, points, "#16816e")
            x = min(1, self.current_raw / SENSOR_MAX)
            y = map_pressure(self.current_raw, self.settings) / SENSOR_MAX
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e37c32"))
            painter.drawEllipse(QRectF(rect.left() + x * rect.width() - 4, rect.bottom() - y * rect.height() - 4, 8, 8))
            label = "Sensor pressure →  (0–100%)"
        else:
            now = time.time()
            visible = [sample for sample in self.samples if now - 10 <= sample[1] <= now]
            self.draw_trace(
                painter,
                rect,
                [((sample[1] - now + 10) / 10, sample[2] / SENSOR_MAX) for sample in visible],
                "#3281c2",
                dashed=True,
            )
            self.draw_trace(
                painter, rect, [((sample[1] - now + 10) / 10, sample[3] / SENSOR_MAX) for sample in visible], "#16816e"
            )
            label = "Last 10 seconds → now · sensor (blue), mapped (green)"
        painter.setPen(text)
        painter.drawText(QRectF(32, self.height() - 24, self.width() - 40, 20), Qt.AlignmentFlag.AlignCenter, label)

    @staticmethod
    def draw_trace(painter: QPainter, rect: QRectF, points: list[tuple], color: str, dashed: bool = False) -> None:
        path = QPainterPath()
        for index, (x, y) in enumerate(points):
            px, py = rect.left() + x * rect.width(), rect.bottom() - y * rect.height()
            if index == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        painter.setPen(QPen(QColor(color), 2, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class PressurePanel(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.stream = None
        self.sequence = 0
        self.peak_raw = 0
        self.current_raw = 0
        self.current_mapped = 0
        self.range_warning = False
        row = QHBoxLayout(self)
        charts = QVBoxLayout()
        self.readings = QLabel("Sensor: 0%  ·  Mapped: 0%  ·  Peak sensor: 0%")
        charts.addWidget(self.readings)
        history_box = QGroupBox("Pressure over time — current driver response")
        history_layout = QVBoxLayout(history_box)
        self.history = PressurePlot()
        history_layout.addWidget(self.history)
        charts.addWidget(history_box, 1)
        curve_box = QGroupBox("Response preview — Save changes to apply")
        curve_layout = QVBoxLayout(curve_box)
        self.response = PressurePlot(curve=True)
        curve_layout.addWidget(self.response)
        charts.addWidget(curve_box, 1)
        self.support = QLabel("Move the pen and make a few comfortable strokes.")
        self.support.setWordWrap(True)
        charts.addWidget(self.support)
        row.addLayout(charts, 2)
        controls = QGroupBox("Pressure feel")
        controls.setMinimumWidth(270)
        controls.setMaximumWidth(330)
        layout = QVBoxLayout(controls)
        self.preset = QComboBox()
        self.presets = [PressureSettings(), PressureSettings(0.65, 0.7), PressureSettings(1, 1.5), None]
        for label in ("Linear (unchanged sensor response)", "Light touch", "Firm", "Custom"):
            self.preset.addItem(label)
        self.preset.currentIndexChanged.connect(self.choose_preset)
        layout.addWidget(self.preset)
        form = QFormLayout()
        self.full_input = QDoubleSpinBox()
        self.full_input.setRange(10, 100)
        self.full_input.setDecimals(1)
        self.full_input.setSuffix("% sensor")
        self.full_input.setSingleStep(5)
        self.full_input.valueChanged.connect(self.edited)
        form.addRow("Full output at", self.full_input)
        self.deadzone = QDoubleSpinBox()
        self.deadzone.setRange(0, 20)
        self.deadzone.setDecimals(1)
        self.deadzone.setSuffix("% sensor")
        self.deadzone.valueChanged.connect(self.edited)
        form.addRow("Ignore below", self.deadzone)
        layout.addLayout(form)
        layout.addWidget(QLabel("Softer ← response curve → Firmer"))
        self.curve_slider = QSlider(Qt.Orientation.Horizontal)
        self.curve_slider.setRange(20, 300)
        self.curve_slider.valueChanged.connect(self.edited)
        layout.addWidget(self.curve_slider)
        self.curve_description = QLabel()
        layout.addWidget(self.curve_description)
        explanation = QLabel(
            "Lower ‘Full output at’ to reach 100% with less force. Move the curve left to boost light strokes. Sensor readings stay unchanged."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addStretch()
        clear = QPushButton("Clear graph and peak")
        clear.clicked.connect(self.clear)
        layout.addWidget(clear)
        peak = QPushButton("Use measured peak as 100%")
        peak.clicked.connect(self.use_peak)
        layout.addWidget(peak)
        instruction = QLabel(
            "Clear the graph, make a few comfortable strokes, then use the measured peak. Pressure follows force, not how long you hold. Do not force the pen harder."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        row.addWidget(controls, 1)
        self.set_settings(PressureSettings())

    def settings(self) -> PressureSettings:
        return PressureSettings.from_dict({
            "full_input": self.full_input.value() / 100,
            "gamma": self.curve_slider.value() / 100,
            "deadzone": self.deadzone.value() / 100,
        })

    def set_settings(self, settings: PressureSettings) -> None:
        for widget in (self.full_input, self.deadzone, self.curve_slider, self.preset):
            widget.blockSignals(True)
        self.full_input.setValue(settings.full_input * 100)
        self.deadzone.setValue(settings.deadzone * 100)
        self.curve_slider.setValue(round(settings.gamma * 100))
        self.preset.setCurrentIndex(next((index for index, preset in enumerate(self.presets) if preset == settings), 3))
        for widget in (self.full_input, self.deadzone, self.curve_slider, self.preset):
            widget.blockSignals(False)
        self.update_preview()

    def choose_preset(self, index: int) -> None:
        preset = self.presets[index]
        if preset is not None:
            self.set_settings(preset)
            self.changed.emit()

    def edited(self, *_args) -> None:
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(3)
        self.preset.blockSignals(False)
        self.update_preview()
        self.changed.emit()

    def update_preview(self) -> None:
        try:
            self.response.settings = self.settings()
            gamma = self.response.settings.gamma
            self.curve_description.setText(
                "Linear" if gamma == 1 else "Boosts light strokes" if gamma < 1 else "Firmer response"
            )
            self.feedback.setText("Preview only until you save.")
            self.response.update()
        except ValueError as exc:
            self.feedback.setText(str(exc))

    def clear(self) -> None:
        self.history.samples.clear()
        self.peak_raw = 0
        self.feedback.setText("Make a few comfortable strokes now; no extra force needed.")
        self.refresh_readings()
        self.history.update()

    def use_peak(self) -> None:
        if self.range_warning:
            self.feedback.setText("Sensor range needs verification before peak calibration.")
            return
        if self.peak_raw < SENSOR_MAX * 0.1:
            self.feedback.setText("No useful peak yet. Clear the graph and make a comfortable stroke first.")
            return
        self.full_input.setValue(min(100, self.peak_raw / SENSOR_MAX * 100))
        self.feedback.setText("Measured peak selected. Save changes to apply it.")

    def update_stream(
        self,
        instance: tuple,
        samples: list,
        supported: bool,
        pen: dict | None,
        max_seen: int = 0,
        out_of_range: int = 0,
    ) -> None:
        if instance != self.stream:
            self.stream = instance
            self.sequence = 0
            self.current_raw = self.current_mapped = 0
            self.range_warning = False
            self.clear()
        if not supported:
            self.support.setText("Restart the driver once to enable live pressure history.")
            return
        self.support.setText(
            "Blue: unchanged sensor pressure. Green: mapped driver pressure. The response preview shows unsaved adjustments."
        )
        self.range_warning = out_of_range > 0
        if self.range_warning:
            self.support.setText(
                f"Sensor range warning: observed raw {max_seen}, above the expected {SENSOR_MAX}. Verify decoding before calibrating."
            )
        for sample in samples:
            if len(sample) != 4 or sample[0] <= self.sequence:
                continue
            self.sequence = sample[0]
            self.history.samples.append(sample)
            self.peak_raw = max(self.peak_raw, sample[2])
        self.current_raw = pen["pressure"] if pen else 0
        self.current_mapped = pen.get("mapped_pressure", self.current_raw) if pen else 0
        self.response.current_raw = self.current_raw
        self.refresh_readings()
        self.history.update()
        self.response.update()

    def refresh_readings(self) -> None:
        self.readings.setText(
            f"Sensor: {self.current_raw / SENSOR_MAX:.0%}  ·  Mapped: {self.current_mapped / SENSOR_MAX:.0%}  ·  Peak sensor: {self.peak_raw / SENSOR_MAX:.0%}"
        )
