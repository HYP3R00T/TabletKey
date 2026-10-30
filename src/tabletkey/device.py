"""Device-scoped Linux access: read-only capture or explicit standalone initialization."""

import fcntl
import os
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

VENDOR_ID = 0x2FEB
PRODUCT_ID = 0x000B


@dataclass(frozen=True)
class Interface:
    path: str
    interface_number: int

    def to_dict(self) -> dict:
        return asdict(self)


def kernel_interfaces(root: Path = Path("/sys/class/hidraw")) -> list[Interface]:
    """Read sysfs metadata for this model only, including hidden device nodes."""
    found = []
    for node in sorted(root.glob("hidraw*")):
        try:
            fields = dict(
                line.split("=", 1) for line in (node / "device/uevent").read_text().splitlines() if "=" in line
            )
            _, vendor, product = fields.get("HID_ID", "::").split(":")
            if int(vendor, 16) != VENDOR_ID or int(product, 16) != PRODUCT_ID:
                continue
            number_path = (node / "device").resolve().parent / "bInterfaceNumber"
            number = int(number_path.read_text().strip(), 16) if number_path.exists() else -1
            found.append(Interface(f"/dev/{node.name}", number))
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda item: (item.interface_number, item.path))


def discover() -> list[Interface]:
    return kernel_interfaces()


class HidrawHandle:
    """A separate nonblocking, read-only file descriptor for a target interface."""

    def __init__(self, path: str, writable: bool = False):
        access = os.O_RDWR if writable else os.O_RDONLY
        self.fd = os.open(path, access | os.O_NONBLOCK | os.O_CLOEXEC)

    def read(self, size: int) -> bytes:
        try:
            data = os.read(self.fd, size)
        except BlockingIOError:
            return b""
        if not data:
            raise OSError("HID interface disconnected (end of stream)")
        return data

    def close(self) -> None:
        os.close(self.fd)


def open_interfaces(interfaces: list[Interface]) -> list[tuple[Interface, HidrawHandle]]:
    """Open all interfaces or close everything; partial capture is misleading."""
    opened = []
    try:
        for interface in interfaces:
            handle = HidrawHandle(interface.path)
            opened.append((interface, handle))
    except BaseException:
        for _, handle in opened:
            handle.close()
        raise
    return opened


def otd_running(proc_root: Path = Path("/proc")) -> bool:
    """Look at executable names only, never unrelated process command lines."""
    for process in proc_root.glob("[0-9]*"):
        try:
            if (process / "exe").readlink().name in {"OpenTabletDriver.Daemon", "otd-daemon"}:
                return True
        except OSError:
            continue
    return False


def open_standalone_interfaces(interfaces: list[Interface]) -> list[tuple[Interface, HidrawHandle]]:
    """Initialize only the verified vendor interface, retaining other handles for diagnostics."""
    vendors = [item for item in interfaces if item.interface_number == 2]
    if len(vendors) != 1:
        raise OSError("Expected exactly one VO1060 vendor interface (USB interface 2)")
    opened = []
    try:
        for interface in interfaces:
            handle = HidrawHandle(interface.path, writable=interface.interface_number == 2)
            opened.append((interface, handle))
            raw_info = bytearray(8)
            fcntl.ioctl(handle.fd, 0x80084803, raw_info, True)  # HIDIOCGRAWINFO
            bus, vendor_id, product_id = struct.unpack("IHH", raw_info)
            if (bus, vendor_id, product_id) != (3, VENDOR_ID, PRODUCT_ID):
                raise OSError("HID identity changed during open; refusing initialization")
        vendor = next(handle for interface, handle in opened if interface.interface_number == 2)
        for report in (bytes.fromhex("09 01 04 00 00 00 00 00 00"), bytes.fromhex("09 02 02 00 00 00 00 00 00")):
            if os.write(vendor.fd, report) != len(report):
                raise OSError("Incomplete VO1060 initialization write")
    except BaseException:
        for _, handle in opened:
            handle.close()
        raise
    return opened


def grab_kernel_inputs(root: Path = Path("/sys/class/input")) -> list:
    """Suppress duplicate native events only for this USB tablet, never other input."""
    from evdev import InputDevice

    grabbed = []
    try:
        for node in sorted(root.glob("event*")):
            try:
                vendor = int((node / "device/id/vendor").read_text().strip(), 16)
                product = int((node / "device/id/product").read_text().strip(), 16)
            except (OSError, ValueError):
                continue
            if (vendor, product) != (VENDOR_ID, PRODUCT_ID):
                continue
            handle = InputDevice(f"/dev/input/{node.name}")
            try:
                if (handle.info.vendor, handle.info.product) != (VENDOR_ID, PRODUCT_ID):
                    raise OSError("Input identity changed during open; refusing grab")
                handle.grab()
            except BaseException:
                handle.close()
                raise
            grabbed.append(handle)
    except BaseException:
        for handle in grabbed:
            handle.close()
        raise
    return grabbed
