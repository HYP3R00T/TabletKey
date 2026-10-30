"""TabletKey diagnostic commands."""

import argparse
import math
import os
import sys
from pathlib import Path

from tabletkey.capture import record, summarize
from tabletkey.device import discover, kernel_interfaces


def positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be a finite positive number")
    return seconds


def doctor() -> int:
    print("TabletKey | VEIKK VO1060 | USB 2feb:000b")
    devices = discover()
    for device in devices:
        print(f"{device.path} interface={device.interface_number} readable={os.access(device.path, os.R_OK)}")
    kernel_paths = [item.path for item in kernel_interfaces()]
    for path in kernel_paths:
        print(f"Kernel sees {path}; device node {'visible' if Path(path).exists() else 'hidden or unavailable'}")
    print("Read-only diagnostics: no device initialization, key injection, or OTD settings changes.")
    if not devices:
        print("No accessible HID interfaces. Run on the host desktop, outside a devcontainer/sandbox.")
        if not kernel_paths:
            print("Check the USB connection. This tool supports only the VO1060 (2feb:000b).")
        return 1
    if any(not Path(device.path).exists() for device in devices):
        print("Target device nodes are hidden or unavailable. Run on the host desktop outside a sandbox.")
        return 1
    if any(not os.access(device.path, os.R_OK) for device in devices):
        print("Read permission is missing. Review device-specific udev access; do not run the app as root.")
        return 1
    print("Interfaces are visible. A record command will test opening them alongside OTD.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TabletKey: read-only VO1060 hardware diagnostics")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check target interfaces and device-node visibility")
    capture = commands.add_parser("record", help="Record all target HID interfaces without changing device mode")
    capture.add_argument("--label", required=True, help="Physical action, e.g. top-button or wheel-clockwise")
    capture.add_argument("--seconds", type=positive_seconds, default=15.0)
    capture.add_argument("--output", type=Path, required=True, help="New JSONL file; never overwrite existing evidence")
    summary = commands.add_parser("inspect", help="Summarize report variation in a saved capture")
    summary.add_argument("capture", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor()
        if args.command == "record":
            if not args.label.strip():
                parser.error("--label must not be blank")
            return record(args.output, args.label, args.seconds, sys.stdout)
        summarize(args.capture, sys.stdout)
        return 0
    except (OSError, ValueError) as exc:
        print(f"tabletkey: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
