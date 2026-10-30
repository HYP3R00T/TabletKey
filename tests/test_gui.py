import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tabletkey import gui
from tabletkey.config import Settings


def test_live_highlighting_and_mapping_editor(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(gui.ipc, "status", lambda: {"running": False})
    app = QApplication.instance() or QApplication([])
    window = gui.Window()
    window.timer.stop()
    try:
        window.update_status({
            "running": True,
            "pid": 123,
            "started_at": 1,
            "connected": True,
            "output_active": False,
            "output_error": None,
            "device_error": None,
            "reports": 2,
            "settings": Settings().to_dict(),
            "pressed": ["button_08"],
            "events": [{"sequence": 1, "control": "button_08", "pressed": True}],
        })
        window.tick()
        assert "#de6c31" in window.indicators["button_08"].styleSheet()
        assert "button_08 pressed" in window.events.toPlainText()
        window.bindings["wheel_01"].setText("SCROLL_UP")
        window.bindings["wheel_02"].setText("SCROLL_DOWN")
        window.swap_wheel()
        assert window.bindings["wheel_01"].text() == "SCROLL_DOWN"
        window.bindings["button_08"].setText("INVALID_KEY")
        window.save()
        assert "Unknown keyboard key" in window.message.text()
        assert window.action_future is None
    finally:
        window.close()
        app.processEvents()
