"""Visual controls and binding choices for TabletKey's settings window."""

from importlib.resources import files
from typing import Any, cast

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QKeySequenceEdit, QLabel, QPushButton, QVBoxLayout, QWidget

from tabletkey.config import parse_binding
from tabletkey.pen import MAX_X, MAX_Y
from tabletkey.ui_preferences import DEFAULT_KEY_ORDER

PRESETS = (
    ("Unassigned", "NONE"),
    ("Undo", "CTRL+Z"),
    ("Redo", "CTRL+SHIFT+Z"),
    ("Copy", "CTRL+C"),
    ("Paste", "CTRL+V"),
    ("Cut", "CTRL+X"),
    ("Save", "CTRL+S"),
    ("Select all", "CTRL+A"),
    ("Find", "CTRL+F"),
    ("New tab", "CTRL+T"),
    ("Close tab", "CTRL+W"),
    ("Reload page", "CTRL+R"),
    ("Go back", "ALT+LEFT"),
    ("Go forward", "ALT+RIGHT"),
    ("Zoom in", "CTRL+EQUAL"),
    ("Zoom out", "CTRL+MINUS"),
    ("Scroll up", "SCROLL_UP"),
    ("Scroll down", "SCROLL_DOWN"),
    ("Volume up", "VOLUMEUP"),
    ("Volume down", "VOLUMEDOWN"),
    ("Mute", "MUTE"),
    ("Play / pause", "PLAYPAUSE"),
)


def binding_caption(binding: str) -> str:
    return next((label for label, value in PRESETS if value == binding), binding.replace("+", " + "))


def captured_binding(sequence: QKeySequence) -> str:
    if sequence.isEmpty():
        return "NONE"
    combination = cast(Any, sequence)[0]  # Qt supports indexing; its type stub omits it.
    modifiers, key = combination.keyboardModifiers(), combination.key()
    parts = []
    for flag, name in (
        (Qt.KeyboardModifier.ControlModifier, "CTRL"),
        (Qt.KeyboardModifier.AltModifier, "ALT"),
        (Qt.KeyboardModifier.ShiftModifier, "SHIFT"),
        (Qt.KeyboardModifier.MetaModifier, "SUPER"),
    ):
        if modifiers & flag:
            parts.append(name)
    number = int(key)
    if int(Qt.Key.Key_A) <= number <= int(Qt.Key.Key_Z) or int(Qt.Key.Key_0) <= number <= int(Qt.Key.Key_9):
        name = chr(number)
    elif int(Qt.Key.Key_F1) <= number <= int(Qt.Key.Key_F24):
        name = f"F{number - int(Qt.Key.Key_F1) + 1}"
    else:
        names = {
            Qt.Key.Key_Return: "ENTER",
            Qt.Key.Key_Enter: "ENTER",
            Qt.Key.Key_Escape: "ESC",
            Qt.Key.Key_Tab: "TAB",
            Qt.Key.Key_Backspace: "BACKSPACE",
            Qt.Key.Key_Delete: "DELETE",
            Qt.Key.Key_Insert: "INSERT",
            Qt.Key.Key_Home: "HOME",
            Qt.Key.Key_End: "END",
            Qt.Key.Key_PageUp: "PAGEUP",
            Qt.Key.Key_PageDown: "PAGEDOWN",
            Qt.Key.Key_Left: "LEFT",
            Qt.Key.Key_Right: "RIGHT",
            Qt.Key.Key_Up: "UP",
            Qt.Key.Key_Down: "DOWN",
            Qt.Key.Key_Space: "SPACE",
            Qt.Key.Key_Minus: "MINUS",
            Qt.Key.Key_Equal: "EQUAL",
            Qt.Key.Key_Comma: "COMMA",
            Qt.Key.Key_Period: "DOT",
            Qt.Key.Key_Slash: "SLASH",
            Qt.Key.Key_Backslash: "BACKSLASH",
            Qt.Key.Key_Semicolon: "SEMICOLON",
            Qt.Key.Key_Apostrophe: "APOSTROPHE",
            Qt.Key.Key_BracketLeft: "LEFTBRACE",
            Qt.Key.Key_BracketRight: "RIGHTBRACE",
            Qt.Key.Key_QuoteLeft: "GRAVE",
            Qt.Key.Key_VolumeUp: "VOLUMEUP",
            Qt.Key.Key_VolumeDown: "VOLUMEDOWN",
            Qt.Key.Key_VolumeMute: "MUTE",
            Qt.Key.Key_MediaPlay: "PLAYPAUSE",
        }
        if key == Qt.Key.Key_Plus:
            name = "EQUAL"
            if "SHIFT" not in parts:
                parts.append("SHIFT")
        elif key in names:
            name = names[key]
        else:
            raise ValueError("That key is not supported yet. Choose a preset or record a different shortcut.")
    binding = "+".join([*parts, name])
    parse_binding(binding)
    return binding


class BindingPicker(QWidget):
    changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.value = "NONE"
        self.needs_capture = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.choices = QComboBox()
        for label, value in PRESETS:
            self.choices.addItem(label, value)
        self.choices.addItem("Custom shortcut…", "CUSTOM")
        layout.addWidget(self.choices)
        self.custom = QWidget()
        custom_layout = QVBoxLayout(self.custom)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        self.capture = QKeySequenceEdit()
        self.capture.setMaximumSequenceLength(1)
        self.capture.setToolTip("Click here, press your shortcut, then click outside to finish.")
        custom_layout.addWidget(self.capture)
        self.record_button = QPushButton("Record a shortcut")
        self.record_button.clicked.connect(self.record)
        custom_layout.addWidget(self.record_button)
        layout.addWidget(self.custom)
        self.caption = QLabel("No action assigned")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.choices.currentIndexChanged.connect(self.choose)
        self.capture.editingFinished.connect(self.finish_capture)
        self.set_binding("NONE")

    def binding(self) -> str:
        if self.needs_capture:
            raise ValueError("Record your custom shortcut before saving, or choose a preset.")
        return self.value

    def set_binding(self, value: str) -> None:
        parse_binding(value)
        self.value = value
        self.needs_capture = False
        self.choices.blockSignals(True)
        index = self.choices.findData(value)
        self.choices.setCurrentIndex(index if index >= 0 else self.choices.findData("CUSTOM"))
        self.choices.blockSignals(False)
        self.custom.setVisible(index < 0)
        self.capture.blockSignals(True)
        if index < 0:
            text = value.replace("SUPER", "Meta").replace("LEFTCTRL", "Ctrl")
            self.capture.setKeySequence(QKeySequence(text))
        self.capture.blockSignals(False)
        self.caption.setText("No action assigned" if value == "NONE" else value.replace("+", " + "))

    def choose(self) -> None:
        value = self.choices.currentData()
        self.custom.setVisible(value == "CUSTOM")
        if value == "CUSTOM":
            self.needs_capture = True
            self.caption.setText("Press Record, then type the shortcut you want.")
            return
        self.set_binding(value)
        self.changed.emit(value)

    def record(self) -> None:
        self.needs_capture = True
        self.capture.clear()
        self.capture.setFocus()
        self.caption.setText("Type your shortcut now, then click outside this box.")

    def finish_capture(self) -> None:
        try:
            value = captured_binding(self.capture.keySequence())
            self.value = value
            self.needs_capture = False
            self.caption.setText("No action assigned" if value == "NONE" else value.replace("+", " + "))
            self.changed.emit(value)
        except ValueError as exc:
            self.caption.setText(str(exc))


class TabletView(QWidget):
    control_selected = Signal(str)
    area_changed = Signal(object)
    SOURCE = QRectF(130, 390, 1310, 835)
    WRITING = QRectF(270, 562, 1005, 598)
    KEYS = {
        "button_01": QRectF(317, 435, 76, 78),
        "button_02": QRectF(397, 435, 76, 78),
        "button_04": QRectF(477, 435, 76, 78),
        "button_08": QRectF(556, 435, 130, 78),
        "button_10": QRectF(186, 449, 49, 49),
    }

    def __init__(self, edit_area: bool = False) -> None:
        super().__init__()
        self.edit_area = edit_area
        self.selected = DEFAULT_KEY_ORDER[0]
        self.key_order = list(DEFAULT_KEY_ORDER)
        self.active: set[str] = set()
        self.area = (0.0, 0.0, 1.0, 1.0)
        self.pen: tuple[float, float, float] | None = None
        self.clockwise: str | None = None
        self.drag_mode: str | None = None
        self.anchor = QPointF()
        self.original_area = self.area
        self.image = QPixmap()
        self.image.loadFromData(files("tabletkey").joinpath("resources/vo1060.jpg").read_bytes())
        self.setMinimumSize(360, 240)
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(650, 415)

    def image_rect(self) -> QRectF:
        available = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        scale = min(available.width() / self.SOURCE.width(), available.height() / self.SOURCE.height())
        width, height = self.SOURCE.width() * scale, self.SOURCE.height() * scale
        return QRectF(available.center().x() - width / 2, available.center().y() - height / 2, width, height)

    def project(self, source: QRectF) -> QRectF:
        target = self.image_rect()
        return QRectF(
            target.x() + (source.x() - self.SOURCE.x()) * target.width() / self.SOURCE.width(),
            target.y() + (source.y() - self.SOURCE.y()) * target.height() / self.SOURCE.height(),
            source.width() * target.width() / self.SOURCE.width(),
            source.height() * target.height() / self.SOURCE.height(),
        )

    def writing_rect(self) -> QRectF:
        return self.project(self.WRITING)

    def selection_rect(self) -> QRectF:
        rect = self.writing_rect()
        left, top, right, bottom = self.area
        return QRectF(
            rect.x() + left * rect.width(),
            rect.y() + top * rect.height(),
            (right - left) * rect.width(),
            (bottom - top) * rect.height(),
        )

    def set_area(self, area: tuple) -> None:
        self.area = area
        self.update()

    def update_live(self, active: set[str], pen: dict | None = None) -> None:
        self.active = active
        self.pen = (pen["x"] / MAX_X, pen["y"] / MAX_Y, pen["pressure"] / 8191) if pen else None
        self.update()

    def control_rects(self) -> dict[str, QRectF]:
        rects = dict(zip(self.key_order, list(self.KEYS.values())[:4], strict=True))
        rects["button_10"] = self.KEYS["button_10"]
        return rects

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(self.image_rect(), self.image, self.SOURCE)
        scale = self.image_rect().width() / self.SOURCE.width()
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(10, round(25 * scale)))
        painter.setFont(font)
        for index, (control, source) in enumerate(self.control_rects().items()):
            rect = self.project(source).adjusted(-2, -2, 2, 2)
            selected = self.selected == control and not self.edit_area
            painter.setPen(QPen(QColor("#54a6fa" if selected else "#eeeeee"), 2 if selected else 1))
            painter.setBrush(QColor(35, 190, 160, 220) if control in self.active else QColor(0, 0, 0, 45))
            if control == "button_10":
                painter.drawEllipse(rect)
            else:
                painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor("white"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(index + 1) if index < 4 else "D")
        wheel = self.project(QRectF(148, 410, 126, 128))
        clockwise = self.clockwise or "wheel_01"
        opposite = "wheel_02" if clockwise == "wheel_01" else "wheel_01"
        for control, start, label, side in (
            (clockwise, -75, "↻" if self.clockwise else "A", 1),
            (opposite, 105, "↺" if self.clockwise else "B", -1),
        ):
            painter.setPen(QPen(QColor("#3ad6b8" if control in self.active else "#a3adb7"), 4))
            painter.drawArc(wheel, start * 16, 150 * 16)
            label_rect = QRectF(wheel.center().x() + side * wheel.width() * 0.36 - 9, wheel.center().y() - 10, 18, 20)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
        if self.edit_area:
            full, selection = self.writing_rect(), self.selection_rect()
            shade = QPainterPath()
            shade.addRect(full)
            shade.addRect(selection)
            painter.fillPath(shade, QColor(0, 0, 0, 110))
            painter.fillRect(selection, QColor(64, 179, 147, 45))
            painter.setPen(QPen(QColor("#5bd5ad"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(selection)
            for point in (selection.topLeft(), selection.topRight(), selection.bottomLeft(), selection.bottomRight()):
                painter.fillRect(QRectF(point.x() - 5, point.y() - 5, 10, 10), QColor("#5bd5ad"))
        if self.pen is not None:
            full = self.writing_rect()
            x, y, pressure = self.pen
            point = QPointF(full.x() + x * full.width(), full.y() + y * full.height())
            painter.setPen(QPen(QColor("white"), 1))
            painter.setBrush(QColor("#f28a43" if pressure else "#65b5ff"))
            radius = 4 + pressure * 8
            painter.drawEllipse(point, radius, radius)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position()
        if not self.edit_area:
            for control, rect in self.control_rects().items():
                if self.project(rect).contains(point):
                    self.control_selected.emit(control)
                    return
            wheel = self.project(QRectF(148, 410, 126, 128))
            if wheel.contains(point):
                code = self.clockwise or "wheel_01"
                self.control_selected.emit(
                    code if point.x() >= wheel.center().x() else ("wheel_02" if code == "wheel_01" else "wheel_01")
                )
            return
        if not self.writing_rect().adjusted(-7, -7, 7, 7).contains(point):
            return
        selected = self.selection_rect()
        for mode, corner in (
            ("tl", selected.topLeft()),
            ("tr", selected.topRight()),
            ("bl", selected.bottomLeft()),
            ("br", selected.bottomRight()),
        ):
            if (point - corner).manhattanLength() < 15:
                self.drag_mode = mode
                break
        else:
            self.drag_mode = "move" if selected.contains(point) else "draw"
        self.anchor = self.normalized(point)
        self.original_area = self.area

    def normalized(self, point: QPointF) -> QPointF:
        rect = self.writing_rect()
        return QPointF(
            min(1.0, max(0.0, (point.x() - rect.x()) / rect.width())),
            min(1.0, max(0.0, (point.y() - rect.y()) / rect.height())),
        )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self.edit_area or self.drag_mode is None:
            return
        point = self.normalized(event.position())
        left, top, right, bottom = self.original_area
        mode = self.drag_mode
        if mode == "move":
            dx = min(1 - right, max(-left, point.x() - self.anchor.x()))
            dy = min(1 - bottom, max(-top, point.y() - self.anchor.y()))
            area = (left + dx, top + dy, right + dx, bottom + dy)
        elif mode == "draw":
            area = (
                min(self.anchor.x(), point.x()),
                min(self.anchor.y(), point.y()),
                max(self.anchor.x(), point.x()),
                max(self.anchor.y(), point.y()),
            )
            if area[2] - area[0] < 0.02 or area[3] - area[1] < 0.02:
                return
        else:
            if mode in ("tl", "bl"):
                left = min(right - 0.02, point.x())
            if mode in ("tr", "br"):
                right = max(left + 0.02, point.x())
            if mode in ("tl", "tr"):
                top = min(bottom - 0.02, point.y())
            if mode in ("bl", "br"):
                bottom = max(top + 0.02, point.y())
            area = (left, top, right, bottom)
        self.area = area
        self.area_changed.emit(area)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.drag_mode = None
