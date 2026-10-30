# TabletKey

**Your tablet. Your shortcuts. Your writing space.**

A standalone Linux driver and visual settings app for the **VEIKK Voila VO1060**.
Give its four keys, dial button, and wheel useful jobs. Keep the pen comfortable, choose where
it writes, and see what the tablet is doing—all from one small Python application.

Built for **COSMIC on Wayland**. Focused on **one device: USB `2feb:000b`**.
No OpenTabletDriver installation required.

[Get started](https://hyp3r00t.github.io/TabletKey/getting-started/) ·
[User guide](https://hyp3r00t.github.io/TabletKey/guide/) ·
[Report a problem](https://github.com/HYP3R00T/TabletKey/issues)

![TabletKey settings: a labelled tablet diagram and shortcut editor](https://raw.githubusercontent.com/HYP3R00T/TabletKey/main/docs/assets/screenshots/buttons.png)

## A Few Good Jobs for Your Tablet

- **Make each control yours.** Pick Undo, Copy, scrolling, volume, or another preset.
  Record a custom keyboard shortcut and give it a name you recognise.
- **Know which key you pressed.** Controls light up on the tablet diagram as you press them.
  Match physical keys and wheel direction without memorising hexadecimal identifiers.
- **Keep a comfortable touch.** Compare raw and mapped pressure, try Light touch,
  or calibrate full output to a comfortable stroke.
- **Choose your writing space.** Select a monitor, rotate the mapping, or drag the active tablet area.
- **See hover detection.** A live timeline separates tablet range exits from report timeouts.
- **Leave it running.** The detached daemon owns input; closing settings leaves your mappings active.
  Reconnect the tablet without restarting the app.

## Start Here

**Release status:** preparing the first PyPI release. The package commands below are the intended
published interface; until that release exists, use the source instructions further down.

On a COSMIC Linux desktop with [uv installed](https://docs.astral.sh/uv/getting-started/installation/):

```sh
# After the first PyPI release: one-time device-access setup
uvx tabletkey setup --install

# Open settings
uvx tabletkey
```

Connect your VO1060, click **Start driver**, set your controls, and click **Save changes**.
The bare command opens the GUI; it does not start the driver automatically.
Run these commands as your normal user. Only the explicit setup command invokes sudo.

For regular use, a persistent tool installation gives the background driver a stable environment:

```sh
uv tool install tabletkey
tabletkey
```

`uvx` uses a cached environment. Stop the daemon before clearing uv's cache or upgrading/removing
its tool environment. Python 3.12+ is required. PySide6 Essentials and evdev are installed as package dependencies;
`cosmic-randr`, udev, and the Linux uinput module come from the operating system.
Some systems need compiler/Python headers to build evdev and system Qt libraries to open the GUI.
See [installation and troubleshooting](https://hyp3r00t.github.io/TabletKey/getting-started/).

### Run from Source Today

```sh
git clone https://github.com/HYP3R00T/TabletKey.git
cd TabletKey
uv sync --locked --managed-python
uv run tabletkey setup --install
uv run tabletkey
```

## One App, Two Parts

**Settings** is the window where you map controls and adjust the pen.
**The daemon** is the background process that reads the tablet and produces Linux input.
Closing the window keeps the daemon running. Stopping the daemon releases input and returns control
to the system's native tablet handling; TabletKey's mappings then stop working.

| After publication | What it does |
|---|---|
| `uvx tabletkey` | Open settings |
| `uvx tabletkey daemon start` | Start in the background; safe to repeat |
| `uvx tabletkey daemon status` | Check process, tablet connection, and output |
| `uvx tabletkey daemon stop` | Release input and stop |
| `uvx tabletkey daemon run` | Run in the terminal until Ctrl+C |
| `uvx tabletkey doctor` | Check device access without changing tablet mode |

From a checkout, replace `uvx tabletkey` with `uv run tabletkey`.
No login service is installed, and setup does not start the daemon automatically.

## A Pen That Fits Your Hand

![TabletKey Pressure tab with response controls and an empty live graph](https://raw.githubusercontent.com/HYP3R00T/TabletKey/main/docs/assets/screenshots/pressure.png)

**Light touch** reaches full output at 65% of the sensor range and boosts lighter strokes.
Prefer your own response? Clear the graph, make comfortable strokes, and choose
**Use measured peak as 100%**. There is no need to press harder to chase the sensor maximum.

The graph separates unchanged sensor pressure from the driver's mapped output.
The response preview changes as you edit; actual output changes when you save.
Pressure is not hover height, and the app does not claim to measure force in newtons.
Screenshots show the real application layout with no fabricated live measurements.

## What Is Supported?

| Area | Current scope |
|---|---|
| Hardware | VEIKK Voila VO1060, USB `2feb:000b` only |
| Desktop | COSMIC Wayland on Linux; other compositors are unverified |
| Pen | Position, pressure response, hover state, barrel buttons |
| Controls | Four keys, dial press, wheel; global shortcuts and scrolling |
| Mapping | Monitor selection, all-monitor mode, crop, rotation |
| Profiles | One global profile; no per-application switching |
| Not implemented | Tilt output, other tablet models, Windows/macOS support, hover smoothing |

**Early software, tested on the owner's device.** Standalone pen movement and wheel scrolling
were physically confirmed after reconnecting without OpenTabletDriver. Comfortable pressure and
hover detection were also confirmed. Multi-monitor crossing, crop/rotation ergonomics,
pressure-aware brush behaviour, and reboot behaviour need more validation.
[Hardware evidence](https://hyp3r00t.github.io/TabletKey/hardware/) separates observations from inferences.

## Device Access and Your Settings

Setup installs target-specific udev rules and a uinput module-loading configuration. The rules grant
the active local session access to the VO1060 and the virtual input interface; they do not grant
access to other physical keyboards or add you to the input group.

The running driver initialises the tablet and exclusively grabs its native input nodes to prevent
duplicate events. It refuses to compete with a running OpenTabletDriver daemon.
Diagnostics stay read-only. Nothing disables or uninstalls another driver automatically.

Settings are stored in `~/.config/tabletkey/` (or `$XDG_CONFIG_HOME/tabletkey/`).
The app preserves unrelated COSMIC input settings and backs up that configuration before its first write.
[The user guide](https://hyp3r00t.github.io/TabletKey/guide/) covers files, mappings, and stopping/uninstalling.

## Work on TabletKey

```sh
uv sync --locked --managed-python
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
uvx zensical serve
```

Tests use fake devices, temporary settings, and offscreen Qt; lifecycle tests disable hardware access.
See the [architecture](https://hyp3r00t.github.io/TabletKey/architecture/) and
[release guide](https://hyp3r00t.github.io/TabletKey/releasing/) for package checks and screenshot refreshes.
Raw captures stay local in ignored `captures/`. Please report the USB identity, desktop, symptoms,
and `doctor` output rather than uploading unrelated input or proprietary driver binaries.

## Credits and License

TabletKey is an independent project, not affiliated with VEIKK. Protocol research references
OpenTabletDriver's public configuration and parsers; there is no OTD runtime dependency.
The bundled tablet schematic is original project artwork. Code, artwork, and documentation are
[MIT licensed](https://github.com/HYP3R00T/TabletKey/blob/main/LICENSE).
