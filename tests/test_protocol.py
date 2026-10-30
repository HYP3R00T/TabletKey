from tabletkey.protocol import ControlEvent, Decoder


def frame(kind, pressed, code):
    return bytes([9, 0x42, kind, pressed, code] + [0] * 8)


def test_all_five_button_press_release_pairs():
    decoder = Decoder()
    for code in (8, 4, 2, 1, 16):
        control = f"button_{code:02x}"
        assert decoder.decode(frame(1, 1, code)) == ControlEvent(control, True)
        assert decoder.decode(frame(1, 1, code)) is None
        assert decoder.decode(frame(1, 0, code)) == ControlEvent(control, False)
        assert not decoder.pressed


def test_wheel_release_does_not_produce_an_extra_step():
    decoder = Decoder()
    assert decoder.decode(frame(3, 1, 2)) == ControlEvent("wheel_02", True)
    assert decoder.decode(frame(3, 0, 2)) == ControlEvent("wheel_02", False)
    assert decoder.decode(frame(3, 0, 2)) is None


def test_unknown_and_pen_reports_are_not_controls():
    decoder = Decoder()
    for data in (b"", b"\x09\x42", frame(1, 1, 3), frame(1, 2, 1), frame(0xA0, 1, 1), bytes(13)):
        assert decoder.decode(data) is None
    assert not decoder.pressed
