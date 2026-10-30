"""Visual settings for TabletKey; the daemon continues owning hardware and output."""

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
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tabletkey import daemon, ipc
from tabletkey.config import Settings, load_settings
from tabletkey.detection_widgets import DetectionPanel
from tabletkey.pressure_widgets import PressurePanel
from tabletkey.protocol import CONTROLS
from tabletkey.ui_preferences import DEFAULT_KEY_ORDER, UiPreferences
from tabletkey.widgets import BindingPicker, TabletView, binding_caption


def paragraph(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TabletKey — VEIKK Voila")
        self.resize(1100, 790)
        self.setMinimumSize(920, 700)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tabletkey-ui")
        self.poll_future: Future | None = None
        self.action_future: Future | None = None
        self.instance: tuple | None = None
        self.sequence = 0
        self.flashes: dict[str, float] = {}
        self.pressed: set[str] = set()
        self.last_pen: dict | None = None
        self.selected = DEFAULT_KEY_ORDER[0]
        self.learning_clockwise = False
        self.matching_keys: list[str] | None = None
        self.loading = True
        self.saving = False
        self.preferences = UiPreferences()
        self.bindings: dict[str, BindingPicker] = {}
        content = QWidget()
        self.setCentralWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("TabletKey")
        title.setStyleSheet("font-size: 26px; font-weight: 600;")
        header.addWidget(title)
        header.addWidget(QLabel("VEIKK Voila · VO1060"))
        header.addStretch()
        self.start_button = QPushButton("Start driver")
        self.stop_button = QPushButton("Stop driver")
        self.start_button.clicked.connect(lambda: self.execute(daemon.start, "Driver started."))
        self.stop_button.clicked.connect(lambda: self.execute(daemon.stop, "Driver stopped."))
        header.addWidget(self.start_button)
        header.addWidget(self.stop_button)
        layout.addLayout(header)
        self.status_label = paragraph("Checking driver…")
        layout.addWidget(self.status_label)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.controls_page(), "Buttons && wheel")
        self.tabs.addTab(self.pen_page(), "Pen && display")
        self.pressure_panel = PressurePanel()
        self.pressure_panel.changed.connect(self.mark_dirty)
        self.tabs.addTab(self.pressure_panel, "Pressure")
        self.detection_panel = DetectionPanel()
        self.tabs.addTab(self.detection_panel, "Pen detection")
        layout.addWidget(self.tabs, 1)
        bottom = QHBoxLayout()
        self.output_enabled = QCheckBox("Enable tablet output")
        self.output_enabled.setToolTip("Pause pen, shortcuts, and scrolling without stopping the driver.")
        self.output_enabled.toggled.connect(self.mark_dirty)
        bottom.addWidget(self.output_enabled)
        bottom.addStretch()
        self.load_button = QPushButton("Discard changes")
        self.save_button = QPushButton("Save changes")
        self.save_button.setDefault(True)
        self.save_button.setStyleSheet("padding: 7px 18px; font-weight: 600;")
        self.load_button.clicked.connect(self.load)
        self.save_button.clicked.connect(self.save)
        bottom.addWidget(self.load_button)
        bottom.addWidget(self.save_button)
        layout.addLayout(bottom)
        self.message = paragraph("Closing this window leaves the driver running.")
        layout.addWidget(self.message)
        self.activity_button = QPushButton("Show activity")
        self.activity_button.setCheckable(True)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumBlockCount(80)
        self.events.setMaximumHeight(110)
        self.events.hide()
        self.activity_button.toggled.connect(self.toggle_activity)
        layout.addWidget(self.activity_button)
        layout.addWidget(self.events)
        self.load()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

    def controls_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(12, 12, 12, 12)
        left = QVBoxLayout()
        self.control_hint = paragraph(
            "Click a control in the picture, or press it on your tablet, to choose its action."
        )
        left.addWidget(self.control_hint)
        self.tablet = TabletView()
        self.tablet.control_selected.connect(self.select_control)
        left.addWidget(self.tablet, 1)
        chips = QGridLayout()
        self.chips = chips
        self.control_buttons: dict[str, QPushButton] = {}
        for index, control in enumerate(CONTROLS):
            button = QPushButton()
            button.setCheckable(True)
            button.setMinimumHeight(47)
            button.clicked.connect(lambda checked=False, code=control: self.select_control(code))
            self.control_buttons[control] = button
            chips.addWidget(button, index // 4, index % 4)
        left.addLayout(chips)
        row.addLayout(left, 2)
        editor = QGroupBox("Selected control")
        editor.setMinimumWidth(270)
        editor.setMaximumWidth(340)
        form = QVBoxLayout(editor)
        self.selected_title = QLabel()
        self.selected_title.setStyleSheet("font-size: 20px; font-weight: 600;")
        form.addWidget(self.selected_title)
        form.addWidget(QLabel("Name"))
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(40)
        self.name_field.textEdited.connect(self.rename_selected)
        form.addWidget(self.name_field)
        form.addWidget(QLabel("Action"))
        self.binding_stack = QStackedWidget()
        for control in CONTROLS:
            picker = BindingPicker()
            picker.changed.connect(self.binding_changed)
            self.bindings[control] = picker
            self.binding_stack.addWidget(picker)
        form.addWidget(self.binding_stack)
        form.addWidget(paragraph("Choose a common action from the list, or record your own keyboard shortcut."))
        form.addStretch()
        self.match_keys_button = QPushButton("Match the four keys to the picture")
        self.match_keys_button.clicked.connect(self.match_keys)
        form.addWidget(self.match_keys_button)
        self.identify_wheel_button = QPushButton("Identify wheel directions")
        self.identify_wheel_button.clicked.connect(self.identify_wheel)
        form.addWidget(self.identify_wheel_button)
        swap = QPushButton("Reverse scrolling")
        swap.clicked.connect(self.swap_wheel)
        form.addWidget(swap)
        form.addWidget(paragraph("Changes apply when you save. Keyboard actions go to the app you are using."))
        row.addWidget(editor, 1)
        return page

    def pen_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(12, 12, 12, 12)
        left = QVBoxLayout()
        left.addWidget(
            paragraph(
                "Drag the green corners to resize the writing area. Drag inside to move it; drag outside to draw a new area."
            )
        )
        self.area_view = TabletView(edit_area=True)
        self.area_view.area_changed.connect(self.area_drawn)
        left.addWidget(self.area_view, 1)
        reset = QPushButton("Use the whole tablet")
        reset.clicked.connect(lambda: self.area_drawn((0.0, 0.0, 1.0, 1.0)))
        left.addWidget(reset)
        self.pen_status = paragraph("Move the pen to see its position on the tablet.")
        left.addWidget(self.pen_status)
        row.addLayout(left, 2)
        editor = QGroupBox("Writing space")
        editor.setMinimumWidth(270)
        editor.setMaximumWidth(340)
        form = QVBoxLayout(editor)
        self.pen_enabled = QCheckBox("Enable pen")
        self.pen_enabled.toggled.connect(self.mark_dirty)
        form.addWidget(self.pen_enabled)
        form.addWidget(QLabel("Where should the pen write?"))
        self.display_choice = QComboBox()
        self.display_choice.addItem("Primary monitor", "auto")
        self.display_choice.addItem("All enabled monitors", "all")
        for screen in QApplication.screens():
            if screen.name():
                self.display_choice.addItem(screen.name(), screen.name())
        self.display_choice.currentIndexChanged.connect(self.mark_dirty)
        form.addWidget(self.display_choice)
        form.addWidget(QLabel("Tablet orientation"))
        self.rotation_choice = QComboBox()
        for rotation, label in ((0, "Normal"), (90, "Rotate right"), (180, "Upside down"), (270, "Rotate left")):
            self.rotation_choice.addItem(label, rotation)
        self.rotation_choice.currentIndexChanged.connect(self.mark_dirty)
        form.addWidget(self.rotation_choice)
        form.addWidget(
            paragraph(
                "The green rectangle is the part of the pad mapped to your selected display. The dot shows the last pen position."
            )
        )
        self.area_summary = paragraph("")
        form.addWidget(self.area_summary)
        precise = QCheckBox("Fine-tune percentages")
        form.addWidget(precise)
        precise_widget = QWidget()
        precise_form = QFormLayout(precise_widget)
        precise_form.setContentsMargins(0, 0, 0, 0)
        self.area_fields: list[QDoubleSpinBox] = []
        for name in ("Left", "Top", "Right", "Bottom"):
            field = QDoubleSpinBox()
            field.setRange(0, 100)
            field.setDecimals(1)
            field.setSuffix("%")
            field.valueChanged.connect(self.area_typed)
            precise_form.addRow(name, field)
            self.area_fields.append(field)
        precise_widget.hide()
        precise.toggled.connect(precise_widget.setVisible)
        form.addWidget(precise_widget)
        form.addStretch()
        row.addWidget(editor, 1)
        return page

    def toggle_activity(self, visible: bool) -> None:
        self.events.setVisible(visible)
        self.activity_button.setText("Hide activity" if visible else "Show activity")

    def mark_dirty(self, *_args) -> None:
        if not self.loading:
            self.message.setText("Unsaved changes · save to apply them to the tablet.")

    def refresh_control_buttons(self) -> None:
        order = [*self.preferences.key_order, "button_10", "wheel_01", "wheel_02"]
        for index, control in enumerate(order):
            button = self.control_buttons[control]
            self.chips.removeWidget(button)
            self.chips.addWidget(button, index // 4, index % 4)
            button.setText(f"{self.preferences.name(control)}\n{binding_caption(self.bindings[control].value)}")
            button.setChecked(control == self.selected)
        self.tablet.key_order = list(self.preferences.key_order)
        self.area_view.key_order = list(self.preferences.key_order)
        self.area_view.clockwise = self.preferences.wheel_clockwise
        self.tablet.clockwise = self.preferences.wheel_clockwise
        self.tablet.update()

    def select_control(self, control: str) -> None:
        if control not in CONTROLS:
            return
        self.selected = control
        self.tablet.selected = control
        self.selected_title.setText(self.preferences.name(control))
        self.name_field.setText(self.preferences.name(control))
        self.binding_stack.setCurrentWidget(self.bindings[control])
        self.refresh_control_buttons()

    def rename_selected(self, text: str) -> None:
        self.preferences.names[self.selected] = text.strip()
        self.selected_title.setText(self.preferences.name(self.selected))
        self.refresh_control_buttons()
        self.mark_dirty()

    def binding_changed(self, _value: str) -> None:
        self.refresh_control_buttons()
        self.mark_dirty()

    def match_keys(self) -> None:
        self.matching_keys = []
        self.learning_clockwise = False
        self.identify_wheel_button.setText("Identify wheel directions")
        self.control_hint.setText(
            "Press the rectangular key NEAREST THE DIAL, then the other three in order away from it."
        )

    def identify_wheel(self) -> None:
        self.matching_keys = None
        self.learning_clockwise = True
        self.control_hint.setText("Turn the wheel CLOCKWISE once. TabletKey will identify both directions.")
        self.identify_wheel_button.setText("Waiting for a clockwise turn…")

    def area_drawn(self, area: tuple) -> None:
        self.area_view.set_area(area)
        for field, value in zip(self.area_fields, area, strict=True):
            field.blockSignals(True)
            field.setValue(value * 100)
            field.blockSignals(False)
        self.area_summary.setText(
            f"Using {(area[2] - area[0]) * 100:.0f}% of the width × {(area[3] - area[1]) * 100:.0f}% of the height"
        )
        self.mark_dirty()

    def area_typed(self) -> None:
        area = tuple(field.value() / 100 for field in self.area_fields)
        if len(area) == 4 and area[0] < area[2] and area[1] < area[3]:
            self.area_view.set_area(area)
            self.area_summary.setText(
                f"Using {(area[2] - area[0]) * 100:.0f}% of the width × {(area[3] - area[1]) * 100:.0f}% of the height"
            )
        self.mark_dirty()

    def load(self) -> None:
        self.loading = True
        try:
            settings = load_settings()
            preference_error = None
            try:
                self.preferences = UiPreferences.load()
            except (OSError, ValueError) as exc:
                self.preferences = UiPreferences()
                preference_error = str(exc)
            for control, picker in self.bindings.items():
                picker.set_binding(settings.bindings[control])
            self.output_enabled.setChecked(settings.output_enabled)
            self.pen_enabled.setChecked(settings.pen.enabled)
            self.pressure_panel.set_settings(settings.pen.pressure)
            if self.display_choice.findData(settings.pen.display) < 0:
                self.display_choice.addItem(settings.pen.display, settings.pen.display)
            self.display_choice.setCurrentIndex(self.display_choice.findData(settings.pen.display))
            self.rotation_choice.setCurrentIndex(self.rotation_choice.findData(settings.pen.rotation))
            self.area_drawn(settings.pen.area)
            self.select_control(self.selected)
            self.learning_clockwise = False
            self.matching_keys = None
            self.identify_wheel_button.setText("Identify wheel directions")
            self.control_hint.setText(
                "Click a control in the picture, or press it on your tablet, to choose its action."
            )
            self.message.setText(
                f"Settings loaded; control names reset because {preference_error}"
                if preference_error
                else "Settings loaded. Closing this window leaves the driver running."
            )
        except (OSError, ValueError) as exc:
            self.message.setText(f"Could not load settings: {exc}")
        finally:
            self.loading = False

    def settings_from_form(self) -> Settings:
        return Settings.from_dict({
            "version": 3,
            "output_enabled": self.output_enabled.isChecked(),
            "bindings": {control: picker.binding() for control, picker in self.bindings.items()},
            "pen": {
                "enabled": self.pen_enabled.isChecked(),
                "display": self.display_choice.currentData(),
                "rotation": self.rotation_choice.currentData(),
                "pressure": {
                    "full_input": self.pressure_panel.settings().full_input,
                    "gamma": self.pressure_panel.settings().gamma,
                    "deadzone": self.pressure_panel.settings().deadzone,
                },
                "area": [field.value() / 100 for field in self.area_fields],
            },
        })

    def save(self) -> None:
        from tabletkey.cli import apply_settings

        try:
            settings = self.settings_from_form()
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        preferences = UiPreferences(
            dict(self.preferences.names), self.preferences.wheel_clockwise, list(self.preferences.key_order)
        )
        self.learning_clockwise = False
        self.matching_keys = None
        self.identify_wheel_button.setText("Identify wheel directions")

        def persist() -> None:
            apply_settings(settings)
            preferences.save()

        self.execute(persist, "Changes saved. Your tablet is ready.")

    def swap_wheel(self) -> None:
        first, second = self.bindings["wheel_01"], self.bindings["wheel_02"]
        before = first.binding()
        first.set_binding(second.binding())
        second.set_binding(before)
        self.refresh_control_buttons()
        self.mark_dirty()

    def execute(self, action, message: str) -> None:
        if self.action_future is not None:
            return

        def perform() -> str:
            action()
            return message

        self.action_future = self.pool.submit(perform)
        self.message.setText("Working…")
        for widget in (
            self.tabs,
            self.start_button,
            self.stop_button,
            self.save_button,
            self.load_button,
            self.output_enabled,
        ):
            widget.setEnabled(False)

    def tick(self) -> None:
        if self.action_future is not None and self.action_future.done():
            try:
                self.message.setText(self.action_future.result())
            except (OSError, ValueError) as exc:
                self.message.setText(str(exc))
            self.action_future = None
            for widget in (
                self.tabs,
                self.start_button,
                self.stop_button,
                self.save_button,
                self.load_button,
                self.output_enabled,
            ):
                widget.setEnabled(True)
        if self.poll_future is not None and self.poll_future.done():
            try:
                self.update_status(self.poll_future.result())
            except (OSError, ValueError) as exc:
                self.status_label.setText(f"Driver unavailable: {exc}")
                self.pressed.clear()
            self.poll_future = None
        if self.poll_future is None:
            self.poll_future = self.pool.submit(ipc.status)
        active = self.pressed | {control for control, until in self.flashes.items() if until > time.monotonic()}
        self.tablet.update_live(active, self.last_pen)
        self.area_view.update_live(active, self.last_pen)
        self.pressure_panel.history.update()
        self.detection_panel.history.update()
        for control, button in self.control_buttons.items():
            button.setStyleSheet("background: #137e70; color: white;" if control in active else "")

    def update_status(self, value: dict[str, Any]) -> None:
        self.detection_panel.update_status(value)
        if not value.get("running"):
            self.status_label.setText("Driver stopped · start it to use the tablet.")
            self.pressed.clear()
            self.last_pen = None
            self.pressure_panel.update_stream((None, None), [], True, None)
            self.pressure_panel.support.setText("Start the driver to see live pressure.")
            return
        state = "Tablet connected" if value.get("connected") else "Waiting for your tablet"
        output = (
            "output ready"
            if value.get("output_active")
            else "output starting"
            if value.get("output_initializing")
            else "output paused"
        )
        self.status_label.setText(" · ".join(["Driver running", state, output]))
        errors = [str(value[key]) for key in ("device_error", "output_error") if value.get(key)]
        if errors:
            self.status_label.setText(" · ".join(errors))
        for display in value.get("displays", []):
            if self.display_choice.findData(display["name"]) < 0:
                self.display_choice.addItem(display["name"], display["name"])
        self.last_pen = value.get("pen")
        if self.last_pen:
            pressure = self.last_pen["pressure"] / 8191 * 100
            mapped = self.last_pen.get("mapped_pressure", self.last_pen["pressure"]) / 8191 * 100
            self.pen_status.setText(f"Pen position shown · sensor {pressure:.0f}% → mapped {mapped:.0f}%")
        instance = (value["pid"], value["started_at"])
        self.pressure_panel.update_stream(
            instance,
            value.get("pressure_history", []),
            value.get("pressure_telemetry", False),
            self.last_pen,
            value.get("pressure_max_seen", 0),
            value.get("pressure_out_of_range", 0),
        )
        events = value.get("events", [])
        if instance != self.instance:
            self.instance = instance
            self.sequence = value.get("sequence", max((event["sequence"] for event in events), default=0))
        self.pressed = set(value.get("pressed", []))
        for event in events:
            if event["sequence"] <= self.sequence:
                continue
            self.sequence = event["sequence"]
            control = event["control"]
            if control not in CONTROLS:
                continue
            if event["pressed"]:
                self.flashes[control] = time.monotonic() + 0.35
                if self.matching_keys is not None and control in self.preferences.key_order:
                    if control not in self.matching_keys:
                        self.matching_keys.append(control)
                    if len(self.matching_keys) == 4:
                        self.preferences.key_order = list(self.matching_keys)
                        self.matching_keys = None
                        self.control_hint.setText("The four keys now match the picture. Save to remember this layout.")
                        self.mark_dirty()
                    else:
                        self.control_hint.setText(
                            f"Key {len(self.matching_keys)} identified. Press the next key away from the dial."
                        )
                if self.learning_clockwise and control.startswith("wheel_"):
                    self.preferences.wheel_clockwise = control
                    self.learning_clockwise = False
                    self.identify_wheel_button.setText("Identify wheel directions")
                    self.control_hint.setText(
                        "Wheel directions identified. Choose an action for each direction, then save."
                    )
                    self.mark_dirty()
                self.select_control(control)
            self.events.appendPlainText(
                f"{self.preferences.name(control)} {'pressed' if event['pressed'] else 'released'}"
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def launch() -> int:
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.show()
    return app.exec()
