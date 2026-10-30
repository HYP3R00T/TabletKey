import pytest

from tabletkey.displays import Display, apply_routes, parse_outputs, route_config

OUTPUTS = """HDMI-A-1 (enabled)
  Position: 1920,0
  Scale: 100%
  Transform: normal
  Xwayland primary: true
  Modes:
    1920x1080 @ 179.961 Hz (current) (preferred)
eDP-1 (disabled)
  Position: 0,0
  Scale: 100%
  Modes:
    1920x1080 @ 60 Hz (preferred)
"""


def test_actual_cosmic_output_shape_and_scaling():
    assert parse_outputs(OUTPUTS) == [Display("HDMI-A-1", 1920, 0, 1920, 1080, True)]
    assert parse_outputs(OUTPUTS.replace("100%", "200%"))[0].width == 960
    with pytest.raises(ValueError):
        parse_outputs(OUTPUTS.replace("(enabled)", "(disabled)"))


def test_ron_update_preserves_other_devices_and_is_idempotent():
    original = """{
    // Existing settings must survive
    "Other tablet": (state: Enabled, map_to_output: Some("HDMI-A-1"), other: (1,2)),
    "Keyboard": (state: Enabled, label: "comma, colon: braces{}"),
}"""
    screens = [Display("HDMI-A-1", 0, 0, 1920, 1080)]
    updated = route_config(original, screens)
    assert '"Other tablet": (state: Enabled, map_to_output: Some("HDMI-A-1"), other: (1,2))' in updated
    assert '"Keyboard": (state: Enabled, label: "comma, colon: braces{}")' in updated
    assert route_config(updated, screens) == updated
    assert updated.count('"TabletKey VO1060 Pen / HDMI-A-1"') == 1


def test_ron_backup_and_malformed_config_never_overwritten(tmp_path):
    path = tmp_path / "input_devices"
    original = '{"Mouse": (state: Enabled),}\n'
    path.write_text(original)
    screens = [Display("main", 0, 0, 100, 100)]
    apply_routes(screens, path)
    assert path.with_name("input_devices.tabletkey.bak").read_text() == original
    first = path.read_text()
    apply_routes(screens, path)
    assert path.read_text() == first
    path.write_text("not valid RON")
    with pytest.raises(ValueError):
        apply_routes(screens, path)
    assert path.read_text() == "not valid RON"
