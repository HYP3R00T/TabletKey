# Standalone architecture

## Ownership

| Module | Responsibility |
|---|---|
| `device.py` | Verify USB identity, initialize interface 2, read hidraw, grab only native VO1060 input |
| `protocol.py` | Captured button and wheel pulse decoding |
| `pen.py` | Pen decoding, tablet-area transform, pressure-sensitive uinput pens |
| `displays.py` | COSMIC output geometry and app-owned per-monitor routing entries |
| `config.py` | Validated settings, atomic writes, version-1 migration |
| `output.py` | Global chords and scrolling with balanced key release |
| `daemon.py` | Connection lifecycle, initialization, output ownership, local IPC |
| `ipc.py` | Private Unix socket with same-user peer checks |
| `cli.py`, `gui.py` | Typer lifecycle/settings commands and the visual PySide6 editor |
| `widgets.py`, `ui_preferences.py` | Photo hit areas, area dragging, shortcut picker, learned physical layout, and control names |
| `setup.py` | Explicit one-time device-scoped udev installation |

There is no OTD library or binary dependency. An optional handoff command can stop the existing
OTD user service. Otherwise, detecting OTD prevents initialization so two drivers do not compete.
Executable names are inspected without reading unrelated process command lines.

## Startup and Shutdown

The daemon holds an OS file lock and owns the local socket. It discovers only `2feb:000b`, checks
access, opens the vendor interface read/write, verifies identity again through HIDIOCGRAWINFO,
and sends two nine-byte output reports. Native evdev nodes are grabbed to prevent duplicate input;
no unrelated mouse or keyboard is grabbed. Initialization or grab failures close all opened handles.

Virtual keyboard/mouse creation and COSMIC pen setup run on a worker so control IPC stays responsive.
A generation counter disposes stale setup results after reload/disconnect. Pen and held keyboard
state are released on stop, disconnect, output replacement, and ambiguous button reports.
Display changes cause output to be rebuilt. Settings UI work is also performed off the Qt UI thread.

Detached start uses the same process as foreground run in a new session, with no terminal file
descriptors. Stop uses IPC rather than trusting a PID file. Ctrl+C/SIGTERM trigger cleanup.
Closing the settings window leaves the daemon running. No persistent user service is installed.

## Pen and COSMIC Mapping

Pen coordinates are 24-bit little-endian values; pressure is a 16-bit field with the configured
maximum of 8191. Invalid out-of-range data is ignored. Native output carries tool proximity, touch,
pressure, position, and two barrel buttons. A half-second report timeout clears stale pen contact.
Stationary-contact behavior needs longer hardware testing; tilt is not implemented.

Single-monitor mode maps the selected tablet rectangle to that monitor. All-monitor mode maps it
to the desktop bounds and selects the virtual pen for the nearest output. The previous pen leaves
proximity before the next enters it. Each virtual device has a COSMIC `map_to_output` entry.
That preserves native tablet pressure rather than implementing pen movement as X11 mouse automation.

COSMIC configuration updates are atomic, backed up once, and limited to TabletKey's device-name
prefix. Existing unrelated entries are retained; malformed or concurrently edited files fail closed.
Connector geometry is queried through the installed `cosmic-randr` tool.

## Defaults and Validation

New version-2 profiles enable pen and wheel output. Shortcut buttons default to NONE.
Version-1 profiles preserve mappings and output pause state while adding default pen settings.
The user-facing wheel codes do not claim calibrated clockwise/counterclockwise labels.

Automated tests use synthetic reports/fake devices and temporary settings. Real lifecycle subprocesses
use `--no-device`, so running tests cannot stop OTD, initialize the physical tablet, or grab its input.
Physical validation is documented separately in [hardware evidence](hardware.md).

## Visual Editor

The editor keeps hardware mappings in the existing version-2 settings schema, including all pen fields.
Display names, physical key order, and learned wheel orientation are UI metadata in `interface.json`.
Learning changes the picture/labels without changing which hardware event a binding belongs to.
Startup ignores buffered historical events when identifying controls; only new presses count.

The official photo is rendered from a bundled resource, with vector overlays for selection, activity,
pen position, and the draggable tablet rectangle. The app does not contact the image host at runtime.
Action presets and Qt shortcut recording both produce validated bindings understood by the existing daemon.
The save path validates a complete profile before updating the driver; it does not omit pen fields.
