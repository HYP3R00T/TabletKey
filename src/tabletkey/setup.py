"""Explicit one-time administrator setup; the driver itself stays unprivileged."""

import os
import subprocess
from importlib.resources import as_file, files
from pathlib import Path

from tabletkey.device import PRODUCT_ID, VENDOR_ID, discover


def physical_input_paths(root: Path = Path("/sys/class/input")) -> list[Path]:
    paths = []
    for node in sorted(root.glob("event*")):
        try:
            identity = tuple(
                int((node / f"device/id/{field}").read_text().strip(), 16) for field in ("vendor", "product")
            )
        except (OSError, ValueError):
            continue
        if identity == (VENDOR_ID, PRODUCT_ID):
            paths.append(node)
    return paths


def access_problem() -> str | None:
    for interface in discover():
        mode = os.R_OK | (os.W_OK if interface.interface_number == 2 else 0)
        if not os.access(interface.path, mode):
            return f"No required access to {interface.path}. Run 'tabletkey setup --install' once in a terminal."
    for node in physical_input_paths():
        if not os.access(f"/dev/input/{node.name}", os.R_OK):
            return f"No access to tablet input {node.name}. Run 'tabletkey setup --install' once in a terminal."
    if not os.access("/dev/uinput", os.W_OK):
        return "No uinput access. Run 'tabletkey setup --install' once in a terminal."
    return None


def rule_text() -> str:
    return files("tabletkey").joinpath("resources/70-tabletkey.rules").read_text(encoding="utf-8")


def install_rules() -> None:
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    with (
        as_file(files("tabletkey").joinpath("resources/70-tabletkey.rules")) as source,
        as_file(files("tabletkey").joinpath("resources/tabletkey-modules.conf")) as modules,
    ):
        commands = [
            [*prefix, "install", "-D", "-m", "0644", str(source), "/etc/udev/rules.d/70-tabletkey.rules"],
            [*prefix, "install", "-D", "-m", "0644", str(modules), "/etc/modules-load.d/tabletkey.conf"],
            [*prefix, "modprobe", "uinput"],
            [*prefix, "udevadm", "control", "--reload-rules"],
        ]
        targets = [Path("/sys/class/hidraw") / Path(item.path).name for item in discover()]
        targets.extend(physical_input_paths())
        if Path("/sys/class/misc/uinput").exists():
            targets.append(Path("/sys/class/misc/uinput"))
        if targets:
            commands.append([*prefix, "udevadm", "trigger", "--action=change", *map(str, targets)])
        commands.append([*prefix, "udevadm", "settle", "--timeout=5"])
        for command in commands:
            try:
                subprocess.run(command, check=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                raise OSError(
                    f"Device-access setup did not finish: {exc}. Re-run setup after checking the error."
                ) from exc
