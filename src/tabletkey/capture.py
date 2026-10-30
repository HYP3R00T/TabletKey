"""Annotated raw captures; decoding waits for verified device evidence."""

import json
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from tabletkey.device import PRODUCT_ID, VENDOR_ID, discover, open_interfaces


def write_record(stream: TextIO, record: dict) -> None:
    stream.write(json.dumps(record, sort_keys=True) + "\n")
    stream.flush()


def record(output: Path, label: str, seconds: float, console: TextIO) -> int:
    interfaces = discover()
    if not interfaces:
        raise OSError("No accessible VO1060 interfaces. Run 'tabletkey doctor' for diagnostics.")
    # Open the output exclusively before hardware access, so existing evidence is never overwritten.
    with output.open("x", encoding="utf-8") as stream:
        write_record(
            stream,
            {
                "type": "session",
                "version": 1,
                "vendor_id": VENDOR_ID,
                "product_id": PRODUCT_ID,
                "started_at": datetime.now(UTC).isoformat(),
                "label": label,
                "requested_seconds": seconds,
                "interfaces": [item.to_dict() for item in interfaces],
            },
        )
        opened = []
        count = 0
        status = "error"
        started = time.monotonic()
        try:
            opened = open_interfaces(interfaces)
            previous: dict[str, bytes] = {}
            print(
                f"Recording {len(opened)} interfaces for {seconds:g}s. Perform only: {label}", file=console, flush=True
            )
            while time.monotonic() - started < seconds:
                for interface, handle in opened:
                    report = bytes(handle.read(1024))
                    if not report:
                        continue
                    elapsed = round(time.monotonic() - started, 6)
                    write_record(
                        stream,
                        {"type": "report", "elapsed": elapsed, "path": interface.path, "hex": report.hex()},
                    )
                    count += 1
                    if previous.get(interface.path) != report:
                        print(f"{elapsed:8.3f}s {interface.path}: {report.hex(' ')}", file=console, flush=True)
                        previous[interface.path] = report
                time.sleep(0.005)
            status = "complete"
        except KeyboardInterrupt:
            status = "interrupted"
        except OSError as exc:
            write_record(stream, {"type": "error", "message": str(exc)})
            raise
        finally:
            for _, handle in opened:
                handle.close()
            write_record(stream, {"type": "end", "status": status, "reports": count})
    print(f"Saved {count} reports to {output} ({status}).", file=console)
    return 0 if status == "complete" else 130


def summarize(path: Path, console: TextIO) -> None:
    """Show per-interface variation without asserting which bytes encode controls."""
    reports: dict[str, Counter] = defaultdict(Counter)
    header = None
    ending = None
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("expected a JSON object")
                kind = row.get("type")
                if line_number == 1:
                    if kind != "session" or row.get("version") != 1:
                        raise ValueError("expected a TabletKey v1 session header")
                    if (row.get("vendor_id"), row.get("product_id")) != (VENDOR_ID, PRODUCT_ID):
                        raise ValueError("capture is not for a VO1060")
                    header = row
                elif kind == "report":
                    if header is None:
                        raise ValueError("missing session header")
                    if ending is not None:
                        raise ValueError("report after end marker")
                    data = bytes.fromhex(row["hex"])
                    if not data or len(data) > 1024:
                        raise ValueError("report length must be 1..1024 bytes")
                    if row["path"] not in {item["path"] for item in header["interfaces"]}:
                        raise ValueError("report refers to an undeclared interface")
                    reports[row["path"]][data] += 1
                elif kind == "end":
                    ending = row
                elif kind != "error":
                    raise ValueError("unrecognized record type")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    if header is None:
        raise ValueError(f"{path}: empty capture")
    status = ending.get("status", "unknown") if ending else "incomplete (no end marker)"
    print(f"Label: {header['label']} | Status: {status}", file=console)
    for interface in header["interfaces"]:
        device_path = interface["path"]
        patterns = reports[device_path]
        print(f"{device_path}: {sum(patterns.values())} reports, {len(patterns)} unique", file=console)
        for length in sorted({len(data) for data in patterns}):
            frames = [data for data in patterns if len(data) == length]
            changes = [i for i in range(length) if len({frame[i] for frame in frames}) > 1]
            print(f"  Length {length}; varying byte offsets (zero-based): {changes}", file=console)
        for data, count in patterns.most_common(12):
            print(f"  {count:6d} × {data.hex(' ')}", file=console)
    print("Raw evidence only; physical button identities and wheel direction are not yet verified.", file=console)
