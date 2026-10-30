"""One foreground or detached process owns hardware, mappings, and local IPC."""

import fcntl
import logging
import os
import selectors
import signal
import socket
import struct
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from logging.handlers import RotatingFileHandler

from evdev.uinput import UInputError

from tabletkey import device
from tabletkey.config import Settings, load_settings, save_settings
from tabletkey.displays import detect_displays
from tabletkey.ipc import receive, request, runtime_dir, send, status
from tabletkey.output import Output
from tabletkey.pen import PenOutput, decode_pen
from tabletkey.protocol import Decoder
from tabletkey.setup import access_problem

LOG = logging.getLogger("tabletkey")


class Daemon:
    def __init__(self, no_device: bool = False) -> None:
        self.no_device = no_device
        self.settings = load_settings()
        self.decoder = Decoder()
        self.output: Output | None = None
        self.pen_output: PenOutput | None = None
        self.pen_reports = 0
        self.pen_state: dict | None = None
        self.grabs: list = []
        self.initialized = False
        self.display_info: list[dict] = []
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tabletkey-output")
        self.output_future: Future | None = None
        self.display_future: Future | None = None
        self.output_generation = 0
        self.future_generation = 0
        self.next_display_scan = 0.0
        self.output_error: str | None = None
        self.device_error: str | None = None
        self.handles: list[tuple[device.Interface, device.HidrawHandle]] = []
        self.events: deque[dict] = deque(maxlen=64)
        self.sequence = 0
        self.reports = 0
        self.running = True
        self.started_at = time.time()
        self.next_scan = 0.0
        self.next_output_retry = 0.0

    def snapshot(self) -> dict:
        return {
            "running": True,
            "no_device": self.no_device,
            "initialized": self.initialized,
            "pen_active": self.pen_output is not None,
            "pen_reports": self.pen_reports,
            "pen": self.pen_state,
            "displays": self.display_info,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "connected": bool(self.handles),
            "interfaces": [item.to_dict() for item, _ in self.handles],
            "device_error": self.device_error,
            "output_active": self.output is not None,
            "output_initializing": self.output_future is not None,
            "output_error": self.output_error,
            "settings": self.settings.to_dict(),
            "pressed": sorted(self.decoder.pressed),
            "reports": self.reports,
            "events": list(self.events),
            "sequence": self.sequence,
        }

    def close_output(self) -> None:
        self.output_generation += 1
        pen, self.pen_output = self.pen_output, None
        if pen is not None:
            try:
                pen.close()
            except OSError:
                LOG.exception("Could not release pen cleanly")
        output, self.output = self.output, None
        if output is not None:
            try:
                output.close()
            except OSError:
                LOG.exception("Could not release virtual input cleanly")

    def disconnect(self) -> None:
        self.close_output()
        for _, handle in self.handles:
            try:
                handle.close()
            except OSError:
                LOG.exception("Could not close HID interface")
        self.handles.clear()
        for handle in self.grabs:
            try:
                handle.close()
            except OSError:
                LOG.exception("Could not release native input grab")
        self.grabs.clear()
        self.initialized = False
        self.pen_state = None
        self.decoder.reset()

    def scan(self) -> None:
        if self.no_device:
            self.device_error = "Hardware access disabled (--no-device)"
            return
        try:
            problem = access_problem()
            if problem:
                raise OSError(problem)
            if device.otd_running():
                if self.handles:
                    self.disconnect()
                self.device_error = "OpenTabletDriver is running. Stop its daemon before starting standalone TabletKey."
                return
            interfaces = device.discover()
            if interfaces == [item for item, _ in self.handles]:
                if not interfaces:
                    self.device_error = "VO1060 not connected"
                return
            self.disconnect()
            if interfaces:
                LOG.info("Initializing VO1060: writing reports 09-01-04 and 09-02-02 to vendor interface 2")
                self.handles = device.open_standalone_interfaces(interfaces)
                self.grabs = device.grab_kernel_inputs()
                self.initialized = True
                self.device_error = None
                LOG.info("Opened %d VO1060 interfaces", len(self.handles))
            else:
                self.device_error = "VO1060 not connected"
        except OSError as exc:
            self.disconnect()
            message = str(exc)
            if message != self.device_error:
                LOG.warning("Device unavailable: %s", message)
            self.device_error = message

    @staticmethod
    def build_output(settings: Settings):
        output = Output(settings)
        pen = None
        displays = []
        try:
            if settings.pen.enabled:
                displays = detect_displays()
                pen = PenOutput(displays, settings.pen.display, settings.pen.area, settings.pen.rotation)
            return output, pen, displays
        except BaseException:
            output.close()
            if pen is not None:
                pen.close()
            raise

    def ensure_output(self) -> None:
        if self.output_future is not None:
            if not self.output_future.done():
                return
            future, self.output_future = self.output_future, None
            try:
                output, pen, displays = future.result()
                if self.future_generation != self.output_generation or not self.handles:
                    output.close()
                    if pen is not None:
                        pen.close()
                else:
                    self.output, self.pen_output = output, pen
                    self.display_info = [item.to_dict() for item in displays]
                    self.output_error = None
                    self.next_display_scan = time.monotonic() + 5
                    LOG.info("Standalone output enabled (pen=%s)", pen is not None)
            except (OSError, ImportError, ValueError, UInputError) as exc:
                message = f"Standalone output unavailable: {exc}"
                if message != self.output_error:
                    LOG.warning(message)
                self.output_error = message
                self.next_output_retry = time.monotonic() + 3
        if not self.settings.output_enabled or not self.handles or self.output is not None:
            return
        if time.monotonic() < self.next_output_retry:
            return
        self.next_output_retry = time.monotonic() + 3
        self.future_generation = self.output_generation
        self.output_future = self.pool.submit(self.build_output, self.settings)

    def refresh_displays(self) -> None:
        if self.display_future is not None and self.display_future.done():
            future, self.display_future = self.display_future, None
            try:
                displays = [item.to_dict() for item in future.result()]
                if self.pen_output is not None and displays != self.display_info:
                    self.close_output()
                    self.next_output_retry = 0
            except (OSError, ValueError) as exc:
                LOG.warning("Display refresh failed: %s", exc)
        if self.pen_output is not None and self.display_future is None and time.monotonic() >= self.next_display_scan:
            self.next_display_scan = time.monotonic() + 5
            self.display_future = self.pool.submit(detect_displays)

    def shutdown(self) -> None:
        self.disconnect()
        self.pool.shutdown(wait=True)
        if self.output_future is not None:
            try:
                output, pen, _ = self.output_future.result()
                output.close()
                if pen is not None:
                    pen.close()
            except (OSError, ValueError, UInputError):
                LOG.exception("Pending output setup ended during shutdown")
            self.output_future = None

    def poll_input(self) -> None:
        if self.pen_output is not None:
            try:
                self.pen_output.expire()
            except OSError as exc:
                self.output_error = str(exc)
                self.close_output()
        for interface, handle in self.handles:
            # Bounded drain: retain responsiveness even during high-rate pen input.
            for _ in range(32):
                try:
                    report = handle.read(1024)
                except OSError as exc:
                    self.device_error = f"Disconnected: {exc}"
                    self.disconnect()
                    self.next_scan = time.monotonic() + 1
                    return
                if not report:
                    break
                self.reports += 1
                pen = decode_pen(report)
                if pen is not None:
                    self.pen_reports += 1
                    self.pen_state = {"x": pen.x, "y": pen.y, "pressure": pen.pressure}
                    if self.pen_output is not None:
                        try:
                            self.pen_output.handle(pen)
                        except OSError as exc:
                            self.output_error = f"Pen output failed: {exc}"
                            self.close_output()
                    continue
                event = self.decoder.decode(report)
                if self.decoder.unverified_button_report:
                    self.close_output()
                    self.decoder.reset()
                    self.output_error = "Unverified button report; held keys released. Use one tablet button at a time."
                    self.next_output_retry = time.monotonic() + 3
                    LOG.warning(self.output_error)
                    continue
                if event is None:
                    continue
                self.sequence += 1
                self.events.append({
                    "sequence": self.sequence,
                    "control": event.control,
                    "pressed": event.pressed,
                    "time": time.time(),
                })
                LOG.debug("%s %s on %s", event.control, "pressed" if event.pressed else "released", interface.path)
                if self.output is not None:
                    try:
                        self.output.handle(event)
                    except OSError as exc:
                        self.output_error = f"Virtual input failed: {exc}"
                        LOG.exception("Virtual input failed")
                        self.close_output()
                        self.next_output_retry = time.monotonic() + 3

    def dispatch(self, message: dict) -> dict:
        command = message.get("command")
        if command == "status":
            return self.snapshot()
        if command == "stop":
            self.running = False
            return {"stopping": True}
        if command in ("reload", "configure"):
            settings = Settings.from_dict(message.get("settings")) if command == "configure" else load_settings()
            if command == "configure":
                save_settings(settings)
            self.close_output()
            self.settings = settings
            self.output_error = None
            self.next_output_retry = 0
            return {"saved": True}
        raise ValueError("Unknown daemon command")

    def serve_client(self, server: socket.socket) -> None:
        connection, _ = server.accept()
        with connection:
            connection.settimeout(0.2)
            try:
                _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    raise ValueError("Client user does not match daemon")
                response = self.dispatch(receive(connection))
            except (OSError, ValueError) as exc:
                response = {"error": str(exc)}
            try:
                send(connection, response)
            except OSError:
                LOG.debug("Control client disconnected")


def run(no_device: bool = False) -> int:
    directory = runtime_dir()
    handler = RotatingFileHandler(directory / "daemon.log", maxBytes=1_000_000, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    lock = (directory / "daemon.lock").open("a")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    selector = selectors.DefaultSelector()
    daemon = None
    acquired = False
    old_handlers = {}
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OSError("TabletKey daemon is already running") from exc
        acquired = True
        daemon = Daemon(no_device=no_device)
        endpoint = directory / "daemon.sock"
        endpoint.unlink(missing_ok=True)
        server.bind(str(endpoint))
        endpoint.chmod(0o600)
        server.listen(8)
        selector.register(server, selectors.EVENT_READ)

        def stop(signum, frame):
            daemon.running = False

        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, stop)
        LOG.info("Daemon running, pid %s", os.getpid())
        while daemon.running:
            if time.monotonic() >= daemon.next_scan:
                daemon.scan()
                daemon.next_scan = time.monotonic() + 1
            daemon.refresh_displays()
            daemon.ensure_output()
            daemon.poll_input()
            if selector.select(timeout=0.01):
                daemon.serve_client(server)
        return 0
    finally:
        if daemon is not None:
            daemon.shutdown()
        selector.close()
        server.close()
        if acquired:
            (directory / "daemon.sock").unlink(missing_ok=True)
        lock.close()
        for signum, old in old_handlers.items():
            signal.signal(signum, old)
        if acquired:
            LOG.info("Daemon stopped")
        LOG.removeHandler(handler)
        handler.close()


def pause_otd() -> None:
    problem = access_problem()
    if problem:
        raise OSError(problem)
    if not device.otd_running():
        return
    try:
        subprocess.run(["systemctl", "--user", "stop", "opentabletdriver.service"], check=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError("Could not pause the OTD user service; close its daemon manually") from exc
    if device.otd_running():
        raise OSError("OTD is still running outside its user service; close its daemon manually")


def start(no_device: bool = False, replace_otd: bool = False) -> dict:
    existing = status()
    if existing.get("running"):
        if existing.get("no_device", False) != no_device:
            raise OSError("Daemon is already running in a different hardware mode; stop it first")
        return existing
    load_settings()  # Report invalid configuration in the invoking terminal.
    if replace_otd and not no_device:
        pause_otd()
    child = subprocess.Popen(
        [sys.executable, "-m", "tabletkey", "daemon", "run", *(["--no-device"] if no_device else [])],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    for _ in range(80):
        time.sleep(0.05)
        current = status()
        if current.get("running"):
            return current
        if child.poll() is not None:
            raise OSError(
                f"Daemon failed to start. Run 'tabletkey daemon run' to see the error. Log: {runtime_dir() / 'daemon.log'}"
            )
    raise OSError("Daemon startup timed out. Check 'tabletkey daemon status' before retrying.")


def stop() -> None:
    if not status().get("running"):
        return
    # A simultaneous Ctrl+C/SIGTERM may already be closing the socket.
    with suppress(FileNotFoundError, ConnectionError):
        request("stop")
    for _ in range(200):
        time.sleep(0.05)
        if not (runtime_dir() / "daemon.sock").exists():
            return
    raise OSError("Daemon is still stopping; inspect daemon.log before retrying.")
