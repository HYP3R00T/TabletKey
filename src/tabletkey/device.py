"""Linux hidraw access without initialization writes, grabs, or driver detachment."""

import os
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

    def __init__(self, path: str):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)

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
