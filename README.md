# TabletKey

A Linux companion for the **VEIKK Voila VO1060** (USB `2feb:000b`).
The goal is live control highlighting, configurable buttons, and system-wide wheel scrolling on Wayland.

**Current implementation:** read-only hardware discovery, labeled raw HID capture, and capture inspection.
Mapping, graphical controls, automatic startup, and scrolling output are not implemented yet.

## Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this repository on the Linux host:

```sh
uv sync
uv run tabletkey doctor
mkdir -p captures
uv run tabletkey record --label top-button --seconds 10 --output captures/top-button.jsonl
uv run tabletkey inspect captures/top-button.jsonl
```

During recording, press and release **only the labeled control** several times.
Keep the pen away from the tablet. Changed raw reports appear immediately in the terminal.
Use a fresh filename for each capture; existing files are never overwritten.
All reports, including repeated reports, are saved. Ctrl+C preserves an interrupted capture.

Repeat for each of the five buttons, wheel clockwise, wheel counterclockwise,
and any wheel press or mode button. Use physical labels (for example, `second-button-from-top`)
instead of guessing which OTD button number it corresponds to. Also capture an untouched idle baseline.
See [hardware investigation](docs/hardware.md) for the evidence and implementation plan.

## Device access

Run on the desktop host: a devcontainer or agent sandbox may expose `/sys` device metadata
while hiding `/dev/hidraw*`. `doctor` reports this distinction.
If nodes are visible but access fails, inspect the existing OpenTabletDriver udev rules and
user device permissions. Do not run the application as root or grant access to all input devices.

The recorder uses Linux hidraw directly (no runtime Python dependencies).
It opens every discovered VO1060 HID interface read-only and reads reports only.
It does not write initialization commands, detach drivers, grab input, edit OTD settings,
or inject keys. Leave OTD running for the initial coexistence test.
Concurrent access and complete report delivery **still require hardware verification**.
A zero-report capture may indicate the wrong device mode or contention, not broken buttons.
An open failure or disconnect ends the session with an error; rerun after reconnecting.

## Development

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

The existing mise, devcontainer, and pre-commit configuration are retained.
Captured reports stay local under ignored `captures/`; share selected captures deliberately.
No Windows driver or REA installation is needed for this first investigation.
