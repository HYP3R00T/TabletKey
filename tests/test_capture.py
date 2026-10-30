import io
import json

import pytest

from tabletkey import capture, device
from tabletkey.cli import main
from tabletkey.device import Interface

INTERFACE = Interface("/dev/hidraw-test", 1)


class FakeHandle:
    def __init__(self, reports=(), failure=False):
        self.reports = iter(reports)
        self.failure = failure
        self.closed = False

    def read(self, size):
        if self.failure:
            raise OSError("disconnected")
        return next(self.reports, [])

    def close(self):
        self.closed = True


def test_record_preserves_identical_frames_and_summary(tmp_path, monkeypatch):
    handle = FakeHandle([[3, 1, 2], [3, 1, 2], [3, 1, 4]])
    monkeypatch.setattr(capture, "discover", lambda: [INTERFACE])
    monkeypatch.setattr(capture, "open_interfaces", lambda _: [(INTERFACE, handle)])
    ticks = iter([0, 0, 0.001, 0.002, 0.003, 0.004, 0.005, 1])
    monkeypatch.setattr(capture.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(capture.time, "sleep", lambda _: None)
    path = tmp_path / "capture.jsonl"
    assert capture.record(path, "top-button", 0.5, io.StringIO()) == 0
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["hex"] for row in rows if row["type"] == "report"] == ["030102", "030102", "030104"]
    assert rows[-1] == {"type": "end", "status": "complete", "reports": 3}
    assert handle.closed
    console = io.StringIO()
    capture.summarize(path, console)
    assert "3 reports, 2 unique" in console.getvalue()
    assert "zero-based): [2]" in console.getvalue()


def test_disconnect_closes_handles_and_marks_incomplete(tmp_path, monkeypatch):
    handle = FakeHandle(failure=True)
    monkeypatch.setattr(capture, "discover", lambda: [INTERFACE])
    monkeypatch.setattr(capture, "open_interfaces", lambda _: [(INTERFACE, handle)])
    path = tmp_path / "capture.jsonl"
    with pytest.raises(OSError, match="disconnected"):
        capture.record(path, "wheel", 1, io.StringIO())
    assert handle.closed
    ending = json.loads(path.read_text().splitlines()[-1])
    assert ending["status"] == "error"


def test_capture_never_overwrites_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "discover", lambda: [INTERFACE])
    path = tmp_path / "capture.jsonl"
    path.write_text("existing evidence")
    with pytest.raises(FileExistsError):
        capture.record(path, "wheel", 1, io.StringIO())
    assert path.read_text() == "existing evidence"


def test_no_device_leaves_no_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "discover", lambda: [])
    path = tmp_path / "capture.jsonl"
    with pytest.raises(OSError, match="No accessible"):
        capture.record(path, "wheel", 1, io.StringIO())
    assert not path.exists()


def test_interrupt_closes_device_and_marks_capture(tmp_path, monkeypatch):
    class InterruptedHandle(FakeHandle):
        def read(self, size):
            raise KeyboardInterrupt

    handle = InterruptedHandle()
    monkeypatch.setattr(capture, "discover", lambda: [INTERFACE])
    monkeypatch.setattr(capture, "open_interfaces", lambda _: [(INTERFACE, handle)])
    path = tmp_path / "capture.jsonl"
    assert capture.record(path, "wheel", 1, io.StringIO()) == 130
    assert handle.closed
    assert json.loads(path.read_text().splitlines()[-1])["status"] == "interrupted"


def test_open_failure_closes_already_opened_interfaces(monkeypatch):
    first = FakeHandle()

    def open_handle(path):
        if path == "/dev/other":
            raise OSError("permission denied")
        return first

    monkeypatch.setattr(device, "HidrawHandle", open_handle)
    with pytest.raises(OSError, match="permission denied"):
        device.open_interfaces([INTERFACE, Interface("/dev/other", 2)])
    assert first.closed


def test_sysfs_fallback_ignores_unrelated_keyboards(tmp_path):
    for name, identity in [("hidraw0", "0003:00002FEB:0000000B"), ("hidraw1", "0003:00001234:0000000B")]:
        directory = tmp_path / name / "device"
        directory.mkdir(parents=True)
        (directory / "uevent").write_text(f"HID_ID={identity}\n")
    assert device.kernel_interfaces(tmp_path) == [Interface("/dev/hidraw0", -1)]


@pytest.mark.parametrize("seconds", ["0", "-1", "nan", "inf"])
def test_cli_rejects_unbounded_duration(seconds):
    with pytest.raises(SystemExit) as exc:
        main(["record", "--label", "wheel", "--seconds", seconds, "--output", "unused.jsonl"])
    assert exc.value.code == 2


def test_corrupt_capture_has_line_number(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"type":"report"}\n')
    with pytest.raises(ValueError, match=r":1: expected a TabletKey"):
        capture.summarize(path, io.StringIO())


def test_hidraw_is_read_only_and_nonblocking(monkeypatch):
    calls = []

    def open_device(path, flags):
        calls.append((path, flags))
        return 42

    def no_data(fd, size):
        raise BlockingIOError

    monkeypatch.setattr(device.os, "open", open_device)
    monkeypatch.setattr(device.os, "read", no_data)
    monkeypatch.setattr(device.os, "close", lambda fd: calls.append(fd))
    handle = device.HidrawHandle(INTERFACE.path)
    assert handle.read(1024) == b""
    handle.close()
    assert calls == [(INTERFACE.path, device.os.O_RDONLY | device.os.O_NONBLOCK | device.os.O_CLOEXEC), 42]


def test_hidraw_eof_is_a_disconnect(monkeypatch):
    monkeypatch.setattr(device.os, "open", lambda *_: 42)
    monkeypatch.setattr(device.os, "read", lambda *_: b"")
    with pytest.raises(OSError, match="disconnected"):
        device.HidrawHandle(INTERFACE.path).read(1024)
