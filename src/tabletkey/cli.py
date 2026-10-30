"""Typer entry points for diagnostics, daemon lifecycle, and global settings."""

import json
import math
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from tabletkey import daemon, ipc
from tabletkey.capture import record, summarize
from tabletkey.config import Settings, config_path, load_settings, parse_binding, save_settings
from tabletkey.device import discover
from tabletkey.displays import detect_displays
from tabletkey.protocol import CONTROLS
from tabletkey.setup import access_problem, install_rules, rule_text

app = typer.Typer(help="TabletKey: standalone VEIKK VO1060 driver for COSMIC/Linux.", no_args_is_help=False)
daemon_app = typer.Typer(help="Start, stop, or inspect the background process.", no_args_is_help=True)
config_app = typer.Typer(
    help="Edit global mappings. Output is disabled until explicitly enabled.", no_args_is_help=True
)
app.add_typer(daemon_app, name="daemon")
app.add_typer(config_app, name="config")


def apply_settings(settings: Settings) -> None:
    if ipc.status().get("running"):
        ipc.request("configure", settings=settings.to_dict())
    else:
        save_settings(settings)


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        gui()


@app.command()
def gui() -> None:
    """Open settings and the live control display. Does not automatically start the daemon."""
    from tabletkey.gui import launch

    raise typer.Exit(launch())


@app.command()
def doctor() -> None:
    """Check target HID visibility and uinput access without injecting input."""
    typer.echo("TabletKey | VEIKK VO1060 | USB 2feb:000b")
    devices = discover()
    healthy = bool(devices)
    if not devices:
        typer.echo("VO1060 not detected. Check USB connection and run on the Linux host.")
    for device in devices:
        visible = Path(device.path).exists()
        readable = os.access(device.path, os.R_OK)
        healthy = healthy and visible and readable
        typer.echo(f"{device.path} interface={device.interface_number} visible={visible} readable={readable}")
    typer.echo(f"uinput accessible={os.access('/dev/uinput', os.W_OK)} (required only for mapped output)")
    typer.echo(f"Settings: {config_path()}")
    problem = access_problem()
    if problem:
        typer.echo(problem)
        healthy = False
    if not healthy:
        typer.echo(
            "Hidden nodes: run outside the sandbox/devcontainer. Permission failures: review target udev access."
        )
    typer.echo("No initialization writes, input injection, or OTD changes performed by doctor.")
    raise typer.Exit(0 if healthy else 1)


def validate_seconds(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise typer.BadParameter("seconds must be a finite positive number")
    return value


@app.command("record")
def record_command(
    label: Annotated[str, typer.Option(help="Physical action, e.g. top-button or wheel-clockwise")],
    output: Annotated[Path, typer.Option(help="New JSONL file; existing evidence is never overwritten")],
    seconds: Annotated[float, typer.Option(callback=validate_seconds)] = 15.0,
) -> None:
    """Record labeled raw reports without changing device mode."""
    if not label.strip():
        raise typer.BadParameter("--label must not be blank")
    raise typer.Exit(record(output, label, seconds, sys.stdout))


@app.command("inspect")
def inspect_command(capture: Path) -> None:
    """Summarize report variation in a saved capture."""
    summarize(capture, sys.stdout)


def print_status(value: dict) -> None:
    if not value.get("running"):
        typer.echo("Daemon: off")
        return
    typer.echo(f"Daemon: running (PID {value['pid']})")
    typer.echo(f"Tablet: {'connected' if value['connected'] else 'waiting/unavailable'} | Reports: {value['reports']}")
    typer.echo(f"Initialization: {value.get('initialized', False)} | Pen active: {value.get('pen_active', False)}")
    typer.echo(f"Mapped output: {'active' if value['output_active'] else 'inactive'}")
    for field in ("device_error", "output_error"):
        if value.get(field):
            typer.echo(value[field])


@daemon_app.command("start")
def daemon_start(
    replace_otd: Annotated[bool, typer.Option(help="Pause the conflicting OTD user service for this session")] = False,
    no_device: Annotated[bool, typer.Option(help="Run lifecycle diagnostics without touching hardware")] = False,
) -> None:
    """Start one detached daemon, or report the existing instance."""
    typer.echo(
        "Diagnostic daemon: hardware access disabled."
        if no_device
        else "Standalone mode initializes the VO1060 and suppresses its duplicate native input while running."
    )
    print_status(daemon.start(no_device=no_device, replace_otd=replace_otd))


@daemon_app.command("run")
def daemon_run(
    replace_otd: Annotated[bool, typer.Option(help="Pause the conflicting OTD user service for this session")] = False,
    no_device: Annotated[bool, typer.Option(help="Run lifecycle diagnostics without touching hardware")] = False,
) -> None:
    """Run in this terminal until Ctrl+C or daemon stop."""
    typer.echo("TabletKey daemon running in foreground. Ctrl+C to stop.")
    typer.echo(
        "Hardware access disabled."
        if no_device
        else "Standalone mode sends VO1060 initialization reports; OpenTabletDriver must be stopped."
    )
    if replace_otd and not no_device:
        daemon.pause_otd()
    raise typer.Exit(daemon.run(no_device=no_device))


@daemon_app.command("status")
def daemon_status(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Report process, hardware connection, and output independently. Off exits with 1."""
    value = ipc.status()
    if json_output:
        typer.echo(json.dumps(value, indent=2))
    else:
        print_status(value)
    raise typer.Exit(0 if value.get("running") else 1)


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Release virtual keys and stop the daemon. Safe to repeat."""
    daemon.stop()
    typer.echo("Daemon: off")


@daemon_app.command("reload")
def daemon_reload() -> None:
    """Reload the settings file, releasing held virtual keys first."""
    ipc.request("reload")
    typer.echo("Settings reloaded.")


@config_app.command("show")
def config_show() -> None:
    """Show the saved global configuration or safe defaults."""
    typer.echo(json.dumps(load_settings().to_dict(), indent=2))


@config_app.command("set")
def config_set(control: str, binding: str) -> None:
    """Set a control to e.g. CTRL+Z, F5, SCROLL_UP, SCROLL_DOWN, or NONE."""
    if control not in CONTROLS:
        raise typer.BadParameter(f"Control must be one of: {', '.join(CONTROLS)}")
    parse_binding(binding)
    settings = load_settings()
    settings.bindings[control] = binding.strip().upper() or "NONE"
    apply_settings(settings)
    typer.echo(f"Saved {control} = {settings.bindings[control]}")


@config_app.command("output")
def config_output(enable: Annotated[bool, typer.Option("--enable/--disable")] = True) -> None:
    """Enable or disable mapped keyboard/scroll output; requires writable /dev/uinput."""
    settings = load_settings()
    settings.output_enabled = enable
    apply_settings(settings)
    typer.echo(f"Mapped output {'enabled' if enable else 'disabled'}. Use daemon status to verify uinput access.")


def main(argv: list[str] | None = None) -> int:
    try:
        app(args=argv)
        return 0
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise
    except (OSError, ValueError) as exc:
        typer.echo(f"tabletkey: {exc}", err=True)
        return 2
    except KeyboardInterrupt:
        return 130


@config_app.command("display")
def config_display(target: str = "auto") -> None:
    """Map the pen to auto, all, or a COSMIC connector such as HDMI-A-1."""
    displays = detect_displays()
    if target not in ("auto", "all") and target not in {item.name for item in displays}:
        raise typer.BadParameter("Selected output is not enabled")
    settings = load_settings()
    settings.pen.display = target
    apply_settings(settings)
    typer.echo(f"Saved pen display: {target}")


@app.command("displays")
def displays_command() -> None:
    """List enabled COSMIC outputs and logical geometry."""
    for display in detect_displays():
        typer.echo(f"{display.name}: {display.width}x{display.height} at {display.x},{display.y}")


@app.command("setup")
def setup_command(
    install: Annotated[bool, typer.Option("--install", help="Install the displayed udev rules using sudo")] = False,
) -> None:
    """Preview or explicitly install device access rules. Never add the user to the input group."""
    typer.echo(rule_text())
    if not install:
        typer.echo("Preview only. Use 'tabletkey setup --install' in a terminal for one-time administrator setup.")
        return
    typer.echo(
        "Installing TabletKey udev rules and /etc/modules-load.d/tabletkey.conf, loading uinput, and refreshing only target devices and uinput."
    )
    install_rules()
    typer.echo("Rules installed. Reconnect the tablet if access has not updated, then run tabletkey doctor.")
