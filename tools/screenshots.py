"""Render the real UI without hardware, daemon access, or the user's profile."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

from tabletkey import gui  # noqa: E402
from tabletkey.config import Settings, save_settings  # noqa: E402
from tabletkey.pressure import PressureSettings  # noqa: E402


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "docs/assets/screenshots"
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with (
        tempfile.TemporaryDirectory(prefix="tabletkey-screenshots-") as temporary,
        patch.dict(os.environ, {"XDG_CONFIG_HOME": temporary}),
        patch.object(gui.ipc, "status", return_value={"running": False}),
    ):
        settings = Settings()
        settings.pen.pressure = PressureSettings(0.65, 0.7)
        save_settings(settings)
        window = gui.Window()
        window.timer.stop()
        window.update_status({"running": False})
        window.resize(1100, 790)
        window.show()
        try:
            for index, name in enumerate(("buttons", "area", "pressure", "detection")):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                if not window.grab().save(str(destination / f"{name}.png")):
                    raise OSError(f"Could not save {name} screenshot")
        finally:
            window.close()
            app.processEvents()
    print(f"Saved four UI screenshots to {destination}")


if __name__ == "__main__":
    main()
