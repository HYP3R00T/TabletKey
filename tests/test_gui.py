import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tabletkey import cli, gui
from tabletkey.ui_preferences import UiPreferences
from tabletkey.widgets import BindingPicker, TabletView, captured_binding


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(gui.ipc, "status", lambda: {"running": False})
    app = QApplication.instance() or QApplication([])
    widget = gui.Window()
    widget.timer.stop()
    yield widget
    widget.close()
    app.processEvents()


def status(events=(), sequence=0, pressed=()):
    return {
        "running": True,
        "pid": 123,
        "started_at": 1,
        "connected": True,
        "output_active": True,
        "pen": None,
        "events": list(events),
        "sequence": sequence,
        "pressed": list(pressed),
    }


def test_live_photo_highlights_and_presets(window):
    window.update_status(status())
    window.update_status(status([{"sequence": 1, "control": "button_04", "pressed": True}], 1, ["button_04"]))
    window.tick()
    assert not window.tablet.image.isNull()
    assert "button_04" in window.tablet.active
    assert window.selected == "button_04"
    assert "Key 3 pressed" in window.events.toPlainText()
    picker = window.bindings["button_04"]
    picker.choices.setCurrentIndex(picker.choices.findData("CTRL+Z"))
    assert picker.binding() == "CTRL+Z"
    assert "Undo" in window.control_buttons["button_04"].text()
    window.swap_wheel()
    assert window.bindings["wheel_01"].binding() == "SCROLL_DOWN"
    assert "OTD" not in window.start_button.text()


def test_save_preserves_pen_area_rotation_display_and_names(window, monkeypatch):
    applied = []
    monkeypatch.setattr(cli, "apply_settings", lambda settings: applied.append(settings))
    window.rotation_choice.setCurrentIndex(window.rotation_choice.findData(90))
    window.display_choice.setCurrentIndex(window.display_choice.findData("all"))
    window.area_drawn((0.1, 0.2, 0.8, 0.9))
    window.pen_enabled.setChecked(False)
    window.rename_selected("Undo brush stroke")
    window.preferences.wheel_clockwise = "wheel_02"
    window.preferences.key_order.reverse()
    window.save()
    assert window.action_future is not None
    window.action_future.result(timeout=2)
    assert len(applied) == 1
    settings = applied[0]
    assert settings.version == 2
    assert settings.pen.area == (0.1, 0.2, 0.8, 0.9)
    assert settings.pen.rotation == 90 and settings.pen.display == "all"
    assert not settings.pen.enabled
    saved = UiPreferences.load()
    assert saved.name("button_01") == "Undo brush stroke"
    assert saved.wheel_clockwise == "wheel_02"
    assert saved.key_order == ["button_08", "button_04", "button_02", "button_01"]


def test_invalid_crop_is_not_saved(window, monkeypatch):
    monkeypatch.setattr(cli, "apply_settings", lambda _: pytest.fail("invalid area must not be applied"))
    window.area_fields[0].setValue(90)
    window.area_fields[2].setValue(10)
    window.save()
    assert window.action_future is None
    assert "positive width" in window.message.text()


def test_direction_learning_ignores_history_and_uses_new_physical_turn(window):
    window.update_status(status([{"sequence": 10, "control": "wheel_01", "pressed": True}], 10))
    window.identify_wheel()
    assert window.preferences.wheel_clockwise is None
    window.update_status(status([{"sequence": 11, "control": "wheel_02", "pressed": True}], 11))
    assert window.preferences.wheel_clockwise == "wheel_02"
    assert window.preferences.name("wheel_02") == "Wheel clockwise"
    assert window.preferences.name("wheel_01") == "Wheel counterclockwise"
    assert not window.learning_clockwise


def test_match_keys_updates_image_positions_without_changing_bindings(window):
    window.update_status(status())
    window.bindings["button_01"].set_binding("CTRL+S")
    window.match_keys()
    for sequence, control in enumerate(("button_08", "button_04", "button_02", "button_01"), 1):
        window.update_status(status([{"sequence": sequence, "control": control, "pressed": True}], sequence))
    assert window.preferences.key_order == ["button_08", "button_04", "button_02", "button_01"]
    assert window.preferences.name("button_08") == "Key 1"
    assert window.tablet.control_rects()["button_08"] == TabletView.KEYS["button_01"]
    assert window.bindings["button_01"].binding() == "CTRL+S"


def test_dragging_area_corner_updates_saved_coordinates(window):
    window.show()
    window.tabs.setCurrentIndex(1)
    QApplication.processEvents()
    view = window.area_view
    start = view.selection_rect().bottomRight().toPoint()
    end = view.writing_rect().center().toPoint()
    QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view, end)
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=end)
    area = window.settings_from_form().pen.area
    assert 0.45 < area[2] < 0.55 and 0.45 < area[3] < 0.55
    assert area[:2] == (0, 0)


def test_clicking_photo_selects_physical_control(window):
    window.show()
    QApplication.processEvents()
    target = window.tablet.project(TabletView.KEYS["button_02"]).center().toPoint()
    QTest.mouseClick(window.tablet, Qt.MouseButton.LeftButton, pos=target)
    assert window.selected == "button_02"
    assert window.selected_title.text() == "Key 2"


@pytest.mark.parametrize(
    "sequence,expected",
    [
        ("Ctrl+Shift+Z", "CTRL+SHIFT+Z"),
        ("Alt+Left", "ALT+LEFT"),
        ("Ctrl+Return", "CTRL+ENTER"),
        ("F5", "F5"),
        ("Ctrl++", "CTRL+SHIFT+EQUAL"),
    ],
)
def test_shortcut_recording_uses_valid_linux_names(sequence, expected):
    assert captured_binding(QKeySequence(sequence)) == expected


def test_custom_selection_requires_a_recorded_shortcut(window):
    picker: BindingPicker = window.bindings["button_08"]
    picker.choices.setCurrentIndex(picker.choices.findData("CUSTOM"))
    with pytest.raises(ValueError, match="Record your custom"):
        picker.binding()
    picker.capture.setKeySequence(QKeySequence("Ctrl+Shift+Z"))
    picker.finish_capture()
    assert picker.binding() == "CTRL+SHIFT+Z"


def test_record_button_captures_keyboard_input(window):
    window.select_control("button_08")
    window.show()
    QApplication.processEvents()
    picker = window.bindings["button_08"]
    picker.choices.setCurrentIndex(picker.choices.findData("CUSTOM"))
    picker.record()
    QTest.keyClick(picker.capture, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    window.name_field.setFocus()
    QApplication.processEvents()
    assert picker.binding() == "CTRL+Z"


def test_physical_key_order_matches_numbered_photo_without_reassigning_actions(window):
    window.update_status(status())
    before = {control: picker.binding() for control, picker in window.bindings.items()}
    for number, control in enumerate(("button_01", "button_02", "button_04", "button_08"), 1):
        window.update_status(status([{"sequence": number, "control": control, "pressed": True}], number))
        window.tick()
        assert window.selected_title.text() == f"Key {number}"
        assert window.tablet.control_rects()[control] == list(TabletView.KEYS.values())[number - 1]
        assert control in window.tablet.active
    assert {control: picker.binding() for control, picker in window.bindings.items()} == before


def test_saved_key_calibration_is_preserved(window):
    custom = UiPreferences(key_order=["button_04", "button_08", "button_01", "button_02"])
    custom.save()
    window.load()
    assert window.preferences.key_order == custom.key_order
    assert window.tablet.key_order == custom.key_order
