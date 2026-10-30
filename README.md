# TabletKey

A **standalone Linux driver** for the VEIKK Voila VO1060 (`2feb:000b`), built with Python,
Typer, PySide6, hidraw, and uinput. The current desktop target is **COSMIC Wayland**.

TabletKey initializes the device, handles pen position/pressure and barrel buttons,
provides global shortcut and wheel mappings, and supports selecting one or all enabled monitors.
The user confirmed pen movement and scrolling after unplug/replug with OTD stopped.
See [hardware evidence](docs/hardware.md) for exactly what has been verified.

## First Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run on the Linux host:

```sh
uv sync --locked --managed-python
uv run tabletkey setup --install
uv run tabletkey daemon start
uv run tabletkey
```

`setup --install` is one-time administrator setup. It displays the rules, asks sudo to install
`/etc/udev/rules.d/70-tabletkey.rules` and `/etc/modules-load.d/tabletkey.conf`, loads the uinput
kernel module, reloads udev rules, and refreshes only the VO1060 nodes
and uinput. It grants the active local session access to this tablet and virtual input output;
it does not add you to the input group or grant access to other physical keyboards.
Run `uv run tabletkey setup` to preview without changing anything.

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
No login service is installed.

To run in the terminal until Ctrl+C:

```sh
uv run tabletkey daemon run
```

Status distinguishes process state, connection, initialization, virtual pen, and mapped output.
`daemon status --json` also includes recent control events and pen-report counters.
Status exits with 1 when off, 0 when running. Logs rotate under `$XDG_RUNTIME_DIR/tabletkey/`.
For lifecycle diagnostics without touching hardware, use `daemon start --no-device`.

## Pen and Monitor Mapping

The **Pen & display** tab shows the real tablet with its active writing rectangle.
Drag the green corner handles to resize it, drag inside to move it, or drag outside to draw a new area.
**Use the whole tablet** resets the selection. Exact percentages remain available under **Fine-tune percentages**.
The pen position dot and pressure percentage show activity while you adjust the preview.

Choose a monitor (or all enabled monitors), an orientation, and whether the pen is enabled.
Click **Save changes** to apply the rectangle, monitor, rotation, and pen state together.

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

## Pressure

The **Pressure** tab separates unchanged sensor readings from mapped driver pressure.
The live graph shows both over the last ten seconds; short input peaks are retained between UI updates.
The response graph previews how sensor pressure will be mapped. It shows the driver's response,
not a measurement of physical force in newtons or a test of the sensor's mechanical linearity.

- **Linear** preserves the previous one-to-one mapping against the verified 8191-count sensor range.
- **Light touch** reaches full output at 65% sensor pressure and boosts lighter strokes.
- **Full output at** selects how much sensor pressure produces 100% mapped pressure.
- Move the curve left to boost light strokes, or right for a firmer response.
- **Ignore below** suppresses low-level noise; leave it at zero unless needed.

For personal calibration, clear the graph, make a few comfortable strokes, then select
**Use measured peak as 100%**. Do not push harder to chase the sensor's maximum.
Click **Save changes** to apply the response. The time graph remains actual mapped telemetry;
unsaved changes affect only the response preview.

Pressure depends on force, not holding duration. The readout resets after a pen-input timeout,
so the last pressure does not stay displayed after lift. Unexpected values above the declared
sensor range produce a diagnostic warning and block peak calibration rather than silently changing
that range. Pressure history is bounded and held in memory, not recorded to disk.
Existing profiles migrate to linear response; the previous pen area, monitor, bindings, and pause state survive.

## Button and Wheel Mappings

The **Buttons & wheel** tab uses the official product photo. Click a pictured control,
choose a control below it, or press one on the tablet. Physical activity flashes green.
The selected control has a blue outline and an action editor beside the picture.

- Choose common actions from the dropdown: Undo, Redo, Copy, Paste, browser actions, scrolling, volume, and more.
- Choose **Custom shortcut**, click **Record a shortcut**, and press the desired keys.
- Give controls your own names, such as "Brush" or "Undo stroke".
- Use **Match the four keys to the picture** to confirm physical order: start nearest the dial and move away.
- Use **Identify wheel directions**, then turn clockwise once. The UI learns both direction names without guessing.
- **Reverse scrolling** swaps the two wheel bindings.

Names, learned layout, and wheel orientation are saved in `interface.json` beside the driver settings.
They do not change hardware identifiers or overwrite existing bindings. The photo and hit areas ship with
the app; no network is needed to display them. Image attribution is in `resources/PHOTO.txt`.

All changes apply when you click **Save changes**; **Discard changes** reloads saved values.
Closing settings leaves the driver running. Per-application profiles are not implemented.
The CLI continues to address hardware identifiers for scripting:

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
