import pytest
from evdev import ecodes

from tabletkey.config import Settings, load_settings, parse_binding, save_settings


def test_config_roundtrip_and_rejection_leaves_saved_file_intact(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings()
    settings.bindings["button_08"] = "CTRL+Z"
    save_settings(settings, path)
    assert load_settings(path) == settings
    original = path.read_text()
    settings.bindings["button_08"] = "RUN_SHELL"
    with pytest.raises(ValueError):
        save_settings(settings, path)
    assert path.read_text() == original
    assert path.stat().st_mode & 0o777 == 0o600


def test_binding_names_validate_before_output_is_created():
    assert parse_binding("CTRL+Z").keys == (ecodes.KEY_LEFTCTRL, ecodes.KEY_Z)
    assert parse_binding("SCROLL_DOWN").scroll == -1
    assert not parse_binding("NONE").keys
    for value in ("CTRL+CTRL", "NO_SUCH_KEY", "CTRL+", "BTN_LEFT"):
        with pytest.raises(ValueError):
            parse_binding(value)


def test_config_rejects_missing_or_extra_controls():
    for mutate in (lambda data: data["bindings"].pop("wheel_01"), lambda data: data["bindings"].update(fake="A")):
        data = Settings().to_dict()
        mutate(data)
        with pytest.raises(ValueError):
            Settings.from_dict(data)


def test_old_settings_migrate_without_losing_bindings_or_pause():
    old = Settings().to_dict()
    old.pop("pen")
    old["version"] = 1
    old["output_enabled"] = False
    old["bindings"]["button_08"] = "CTRL+S"
    restored = Settings.from_dict(old)
    assert restored.version == 2 and restored.pen.enabled
    assert not restored.output_enabled
    assert restored.bindings["button_08"] == "CTRL+S"


def test_pen_crop_rejects_nan_and_empty_area():
    for area in ([0.5, 0, 0.1, 1], [0, 0, float("nan"), 1]):
        data = Settings().to_dict()
        data["pen"]["area"] = area
        with pytest.raises(ValueError):
            Settings.from_dict(data)
