# TabletKey

A **standalone Linux driver** for the VEIKK Voila VO1060 (`2feb:000b`), built with Python,
Typer, PySide6, hidraw, and uinput. The current desktop target is **COSMIC Wayland**.
OpenTabletDriver is not a runtime dependency.

TabletKey initializes the device, handles pen position/pressure and barrel buttons,
provides global shortcut and wheel mappings, and supports selecting one or all enabled monitors.
The user confirmed pen movement and scrolling after unplug/replug with OTD stopped.
See [hardware evidence](docs/hardware.md) for exactly what has been verified.

## First Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run on the Linux host:

```sh
uv sync --locked --managed-python
uv run tabletkey setup --install
uv run tabletkey daemon start --replace-otd
uv run tabletkey
```

`setup --install` is one-time administrator setup. It displays the rules, asks sudo to install
`/etc/udev/rules.d/70-tabletkey.rules` and `/etc/modules-load.d/tabletkey.conf`, loads the uinput
kernel module, reloads udev rules, and refreshes only the VO1060 nodes
and uinput. It grants the active local session access to this tablet and virtual input output;
it does not add you to the input group or grant access to other physical keyboards.
Run `uv run tabletkey setup` to preview without changing anything.

`--replace-otd` explicitly pauses the conflicting OTD user service for this session if present.
It does not disable or uninstall OTD. Without this option, TabletKey refuses to initialize while
OTD is running. On a machine without OTD, plain `daemon start` is sufficient.

The default profile enables the pen over the primary enabled monitor, full tablet area, and wheel
scrolling. Shortcut buttons start unassigned. Older settings retain their bindings and output-pause
flag when migrated; enable output in settings if an older profile was paused.

## Daemon and Settings

```sh
uv run tabletkey daemon start
uv run tabletkey daemon status
uv run tabletkey daemon stop
uv run tabletkey gui
```

The bare `tabletkey` command also opens settings. Start detaches from the terminal and is safe to
repeat. Closing settings leaves the daemon running. Stop releases virtual keys, pen contact, and
native input grabs. Reconnect the tablet while the daemon runs; it rediscovers and initializes it.
No login service is installed. OTD may start again on your next login if its service is still enabled.

To run in the terminal until Ctrl+C:

```sh
uv run tabletkey daemon run --replace-otd
```

Status distinguishes process state, connection, initialization, virtual pen, and mapped output.
`daemon status --json` also includes recent control events and pen-report counters.
Status exits with 1 when off, 0 when running. Logs rotate under `$XDG_RUNTIME_DIR/tabletkey/`.
For lifecycle diagnostics without touching hardware, use `daemon start --no-device`.

## Pen and Monitor Mapping

Settings provides:

- Automatic primary output, a specific enabled monitor, or all enabled monitors.
- Tablet rotation in 90° steps.
- An active tablet rectangle, expressed as left/top/right/bottom percentages.
- Pressure-sensitive pen output and two standard barrel buttons.
- A live position/pressure readout.

```sh
uv run tabletkey displays
uv run tabletkey config display HDMI-A-1
uv run tabletkey config display all
```

For all-monitor mode, normalized tablet coordinates span the logical desktop. TabletKey creates
one virtual pen per target display and transfers proximity as the pen crosses outputs. Gaps are
clamped to the nearest display. Monitor changes are polled and virtual output is rebuilt as needed.

COSMIC routes native tablet input per device. TabletKey therefore maintains only entries named
`TabletKey VO1060 Pen / <connector>` in COSMIC's `input_devices` settings. Existing unrelated
entries are preserved. A first-write backup is saved beside that file as `input_devices.tabletkey.bak`.
Malformed or concurrently modified configuration is rejected rather than overwritten.

Single-monitor movement is verified locally. Pressure-aware drawing, multi-monitor crossing,
rotation/cropping ergonomics, tilt, and multi-button rollover need further hardware/application
validation. Tilt output is not implemented.

## Button and Wheel Mappings

Press a physical control to see its code highlight. The four key codes are `08`, `04`, `02`, `01`
in the recorded press order; `10` is inferred to be the dial-center press.
Wheel codes `01` and `02` are mapped to scroll up/down by default. Their physical direction labels
remain uncalibrated; **Swap wheel mappings** reverses them.

Bindings accept `CTRL+Z`, `CTRL+SHIFT+Z`, `ALT+TAB`, `F5`, `VOLUMEUP`, `SCROLL_UP`,
`SCROLL_DOWN`, or `NONE`. Save applies to a running daemon or persists for the next start.
Global shortcuts go to the focused application or desktop handler, like a keyboard.
There are no per-application profiles yet.

```sh
uv run tabletkey config set button_08 'CTRL+Z'
uv run tabletkey config output --disable
uv run tabletkey config output --enable
```

Pausing output pauses pen, shortcuts, and wheel output. Standalone input remains owned until stop.
Unverified combined-button reports release held keys and pause output briefly, preventing stuck shortcuts.

## Diagnostics and Files

```sh
uv run tabletkey doctor
mkdir -p captures
uv run tabletkey record --label top-button --seconds 10 --output captures/top-button.jsonl
uv run tabletkey inspect captures/top-button.jsonl
```

Doctor and recording stay read-only; they do not initialize or grab the tablet.
Captures stay local under ignored `captures/`; existing evidence is never overwritten.

Settings live at `$XDG_CONFIG_HOME/tabletkey/settings.json` (normally `~/.config/tabletkey/settings.json`).
Manual file edits require `daemon reload`. Runtime files use a private directory under
`$XDG_RUNTIME_DIR`, or a private fallback under `/tmp` if that variable is absent.

Run the driver on the Linux desktop host, not inside a devcontainer or agent sandbox.
It requires access to the target hidraw and native input nodes plus `/dev/uinput`.
Only setup invokes sudo; run the daemon and UI as your normal user.
uv-managed Python includes the headers needed to build evdev; system Python may require development headers.

## Development

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Tests use synthetic reports, fake devices, temporary configuration, and offscreen Qt. Real subprocess
lifecycle tests explicitly disable hardware access. They require local Unix sockets on Linux.
See [architecture](docs/architecture.md) for lifecycle and implementation boundaries.
