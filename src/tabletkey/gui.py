"""A small PySide6 editor; hardware and output remain owned by the daemon."""

import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tabletkey import daemon, ipc
from tabletkey.config import Settings, load_settings
from tabletkey.protocol import CONTROLS

LABELS = {
    "button_08": "Key · 08",
    "button_04": "Key · 04",
    "button_02": "Key · 02",
    "button_01": "Key · 01",
    "button_10": "Dial press · 10*",
    "wheel_01": "Wheel · 01",
    "wheel_02": "Wheel · 02",
}


class Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TabletKey — VO1060")
        self.resize(860, 900)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tabletkey-ui")
        self.poll_future: Future | None = None
        self.action_future: Future | None = None
        self.instance: tuple | None = None
        self.sequence = 0
        self.flashes: dict[str, float] = {}
        self.pressed: set[str] = set()
        self.indicators: dict[str, QLabel] = {}
        self.bindings: dict[str, QLineEdit] = {}
        content = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(content)
        title = QLabel("TabletKey  /  VEIKK VO1060")
        title.setStyleSheet("font-size: 24px; font-weight: 600; padding: 8px 0;")
        layout.addWidget(title)
        self.status_label = QLabel("Checking daemon…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start TabletKey (pause OTD)")
        self.stop_button = QPushButton("Stop daemon")
        self.start_button.clicked.connect(
            lambda: self.execute(lambda: daemon.start(replace_otd=True), "Daemon started")
        )
        self.stop_button.clicked.connect(lambda: self.execute(daemon.stop, "Daemon stopped"))
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        row = QHBoxLayout()
        for control in ("button_10", "button_08", "button_04", "button_02", "button_01"):
            indicator = QLabel(LABELS[control])
            indicator.setMinimumHeight(64)
            indicator.setMargin(10)
            row.addWidget(indicator)
            self.indicators[control] = indicator
        layout.addLayout(row)
        wheel_row = QHBoxLayout()
        for control in ("wheel_01", "wheel_02"):
            indicator = QLabel(LABELS[control])
            indicator.setMinimumHeight(40)
            indicator.setMargin(10)
            wheel_row.addWidget(indicator)
            self.indicators[control] = indicator
        layout.addLayout(wheel_row)
        note = QLabel(
            "Press a physical control to identify its code. *Dial press is inferred from your capture.\n"
            "Wheel direction is uncalibrated: assign scroll up/down, then swap if necessary."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        for control in CONTROLS:
            editor = QLineEdit()
            editor.setPlaceholderText("NONE, CTRL+Z, ALT+TAB, F5, SCROLL_UP…")
            form.addRow(LABELS[control], editor)
            self.bindings[control] = editor
        layout.addLayout(form)
        self.pen_enabled = QCheckBox("Enable pressure-sensitive pen")
        layout.addWidget(self.pen_enabled)
        pen_form = QFormLayout()
        self.display_choice = QComboBox()
        self.display_choice.addItem("Primary monitor (automatic)", "auto")
        self.display_choice.addItem("All enabled monitors", "all")
        for screen in QApplication.screens():
            if screen.name():
                self.display_choice.addItem(screen.name(), screen.name())
        pen_form.addRow("Pen display", self.display_choice)
        self.rotation_choice = QComboBox()
        for rotation in (0, 90, 180, 270):
            self.rotation_choice.addItem(f"{rotation}°", rotation)
        pen_form.addRow("Tablet rotation", self.rotation_choice)
        area_widget = QWidget()
        area_row = QHBoxLayout(area_widget)
        area_row.setContentsMargins(0, 0, 0, 0)
        self.area_fields: list[QDoubleSpinBox] = []
        for name in ("Left", "Top", "Right", "Bottom"):
            area_row.addWidget(QLabel(name))
            field = QDoubleSpinBox()
            field.setRange(0, 100)
            field.setDecimals(1)
            field.setSuffix("%")
            area_row.addWidget(field)
            self.area_fields.append(field)
        pen_form.addRow("Active tablet area", area_widget)
        layout.addLayout(pen_form)
        self.pen_status = QLabel("No pen reports yet")
        layout.addWidget(self.pen_status)
        self.output_enabled = QCheckBox("Enable driver output (pen, shortcuts, and scrolling)")
        layout.addWidget(self.output_enabled)
        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save mappings")
        self.load_button = QPushButton("Reload saved mappings")
        swap = QPushButton("Swap wheel mappings")
        self.save_button.clicked.connect(self.save)
        self.load_button.clicked.connect(self.load)
        swap.clicked.connect(self.swap_wheel)
        for button in (self.save_button, self.load_button, swap):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.message = QLabel("Closing this window leaves the daemon running.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        pen_note = QLabel(
            "Standalone mode: stop OpenTabletDriver before starting TabletKey. Monitor routing is saved for TabletKey devices only."
        )
        pen_note.setWordWrap(True)
        layout.addWidget(pen_note)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumBlockCount(80)
        layout.addWidget(self.events)
        self.load()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

    def load(self) -> None:
        try:
            settings = load_settings()
            for control, editor in self.bindings.items():
                editor.setText(settings.bindings[control])
            self.output_enabled.setChecked(settings.output_enabled)
            self.pen_enabled.setChecked(settings.pen.enabled)
            if self.display_choice.findData(settings.pen.display) < 0:
                self.display_choice.addItem(settings.pen.display, settings.pen.display)
            self.display_choice.setCurrentIndex(self.display_choice.findData(settings.pen.display))
            self.rotation_choice.setCurrentIndex(self.rotation_choice.findData(settings.pen.rotation))
            for field, value in zip(self.area_fields, settings.pen.area, strict=True):
                field.setValue(value * 100)
            self.message.setText("Saved mappings loaded. Use the live highlights to identify controls.")
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc))

    def save(self) -> None:
        from tabletkey.cli import apply_settings

        try:
            settings = Settings.from_dict({
                "version": 1,
                "output_enabled": self.output_enabled.isChecked(),
                "bindings": {
                    control: editor.text().strip().upper() or "NONE" for control, editor in self.bindings.items()
                },
            })
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self.execute(lambda: apply_settings(settings), "Mappings saved; daemon updated if running")

    def swap_wheel(self) -> None:
        first, second = self.bindings["wheel_01"], self.bindings["wheel_02"]
        before = first.text()
        first.setText(second.text())
        second.setText(before)
        self.message.setText("Wheel mappings swapped. Save to apply.")

    def execute(self, action, message: str) -> None:
        if self.action_future is not None:
            return

        def perform() -> str:
            action()
            return message

        self.action_future = self.pool.submit(perform)
        self.message.setText("Working…")
        for button in (self.start_button, self.stop_button, self.save_button, self.load_button):
            button.setEnabled(False)

    def tick(self) -> None:
        if self.action_future is not None and self.action_future.done():
            try:
                self.message.setText(self.action_future.result())
            except (OSError, ValueError) as exc:
                self.message.setText(str(exc))
            self.action_future = None
            for button in (self.start_button, self.stop_button, self.save_button, self.load_button):
                button.setEnabled(True)
        if self.poll_future is not None and self.poll_future.done():
            try:
                self.update_status(self.poll_future.result())
            except (OSError, ValueError) as exc:
                self.status_label.setText(f"Daemon unavailable: {exc}")
                self.pressed.clear()
            self.poll_future = None
        if self.poll_future is None:
            self.poll_future = self.pool.submit(ipc.status)
        now = time.monotonic()
        for control, indicator in self.indicators.items():
            active = control in self.pressed or self.flashes.get(control, 0) > now
            indicator.setStyleSheet(
                "background: #de6c31; color: white; border-radius: 8px; font-weight: 600;"
                if active
                else "background: #30343b; color: #edf1f7; border-radius: 8px;"
            )

    def update_status(self, value: dict[str, Any]) -> None:
        if not value.get("running"):
            self.status_label.setText("Daemon off · no mapped output. Start it here or from the CLI.")
            self.pressed.clear()
            return
        for display in value.get("displays", []):
            if self.display_choice.findData(display["name"]) < 0:
                self.display_choice.addItem(display["name"], display["name"])
        pen = value.get("pen")
        if pen:
            self.pen_status.setText(f"Pen: x={pen['x']} y={pen['y']} pressure={pen['pressure']} / 8191")
        else:
            self.pen_status.setText("No pen reports yet")
        self.status_label.setText(
            f"Daemon running · PID {value['pid']} · "
            f"{'Tablet connected' if value['connected'] else 'Waiting for tablet'} · "
            f"Output {'active' if value['output_active'] else 'inactive'} · {value['reports']} reports\n"
            + " | ".join(str(value[key]) for key in ("device_error", "output_error") if value.get(key))
        )
        instance = (value["pid"], value["started_at"])
        if instance != self.instance:
            self.instance = instance
            self.sequence = 0
        self.pressed = set(value["pressed"])
        for event in value["events"]:
            if event["sequence"] <= self.sequence:
                continue
            self.sequence = event["sequence"]
            if event["pressed"]:
                self.flashes[event["control"]] = time.monotonic() + 0.35
            self.events.appendPlainText(f"{event['control']} {'pressed' if event['pressed'] else 'released'}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def launch() -> int:
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.show()
    return app.exec()
