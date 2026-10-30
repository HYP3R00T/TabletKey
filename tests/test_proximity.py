import json
from types import SimpleNamespace

from tabletkey import daemon, pen
from tabletkey.config import Settings
from tabletkey.device import Interface
from tabletkey.proximity import Detection, is_range_exit


def test_exit_requires_exact_observed_pen_report_shape():
    report = bytes.fromhex("0941c0359d0005400000000000")
    assert is_range_exit(report)
    assert pen.decode_pen(report) is None
    assert not is_range_exit(report[:-1])
    assert not is_range_exit(bytes.fromhex("0942c0359d0005400000000000"))
    assert not is_range_exit(bytes.fromhex("0941a0359d0005400000000501"))


def test_detection_retains_brief_exit_and_separates_timing_from_deliberate_absence(monkeypatch):
    detection = Detection()
    detection.received(10)
    detection.received(10.005)
    detection.lost(10.01, "Tablet range exit")
    detection.received(10.015)
    detection.lost(10.52, "Report timeout")
    detection.lost(11, "Report timeout")
    monkeypatch.setattr("tabletkey.proximity.time.monotonic", lambda: 11)
    state = detection.snapshot()
    assert state["range_exits"] == 1 and state["timeouts"] == 1
    assert len(state["history"]) == 4
    assert not state["in_range"]
    assert round(state["max_gap_ms"]) == 5
    assert round(state["last_report_ms"]) == 985
    assert state["reports_last_second"] == 3
    detection.received(20)
    assert round(detection.snapshot()["max_gap_ms"]) == 5


def test_explicit_exit_releases_output_and_pressure_without_waiting_for_timeout(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon(no_device=True)
    frames = iter([
        bytes.fromhex("0941a1359d0005400088130501"),
        bytes.fromhex("0941c0359d0005400000000000"),
    ])
    monkeypatch.setattr(
        worker,
        "handles",
        [(Interface("/dev/fake", 2), SimpleNamespace(read=lambda _: next(frames, b""), close=lambda: None))],
    )
    calls = []
    monkeypatch.setattr(
        worker,
        "pen_output",
        SimpleNamespace(
            handle=lambda _: calls.append("pen"),
            release=lambda: calls.append("release"),
            expire=lambda: None,
            close=lambda: None,
            active=None,
        ),
    )
    worker.poll_input()
    assert calls == ["pen", "release"]
    assert worker.pen_state is not None
    assert worker.pen_state["pressure"] == worker.pen_state["mapped_pressure"] == 0
    assert not worker.pen_state["in_range"]
    assert worker.detection.exits == 1
    assert worker.last_pen_time == 0
    assert worker.pressure_history[-1][2:] == [0, 0]
    # A new hover report restores proximity without contact.
    frames = iter([bytes.fromhex("0941a0c79d0015400000000000")])
    worker.poll_input()
    assert worker.pen_state["in_range"] and worker.pen_state["pressure"] == 0
    assert worker.snapshot()["detection"]["in_range"]
    worker.disconnect()
    assert not worker.snapshot()["detection"]["in_range"]
    worker.shutdown()


def test_transition_storage_and_ipc_remain_bounded(monkeypatch):
    monkeypatch.setattr(daemon, "load_settings", Settings)
    worker = daemon.Daemon(no_device=True)
    for index in range(1000):
        worker.detection.received(index * 2)
        worker.detection.lost(index * 2 + 1, "Tablet range exit")
        worker.add_pressure_sample(5000, 7000)
    for index in range(64):
        worker.events.append({"sequence": index, "control": "button_01", "pressed": True, "time": 1234567890.0})
    assert len(worker.detection.history) == 128
    assert len(worker.detection.recent) == 512
    assert len(json.dumps(worker.snapshot()).encode()) < 65536
    worker.shutdown()
