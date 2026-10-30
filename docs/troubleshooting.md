# When something gets in the way

Start with a read-only check:

```sh
uvx tabletkey doctor
uvx tabletkey daemon status
```

Until the first PyPI release, use `uv run tabletkey` from your checkout instead of `uvx tabletkey`.
Status distinguishes the process, USB connection, initialisation, virtual pen, and mapped output.
A process can be running while output is unavailable.

## “Tablet not detected”

Confirm the USB identity is **`2feb:000b`**. “VEIKK” alone is not enough: other models may have
entirely different protocols. Connect directly and try another cable/port. Run on the desktop host,
not inside a container or sandbox that cannot see `/dev/hidraw*` and `/dev/input/`.

## Permission denied or no uinput access

Run `uvx tabletkey setup` to preview the rules, then `uvx tabletkey setup --install` for explicit
one-time installation. Run the driver as the logged-in desktop user. If refreshed access has not
appeared, unplug/replug the tablet or restart the desktop session. Do not work around access issues
by running the whole app with sudo or granting access to every input device.

## OpenTabletDriver is running

Close its daemon before starting TabletKey. Closing its settings window may leave its daemon running.
TabletKey refuses concurrent operation. The optional `daemon start --replace-otd` explicitly stops
its user service for the session; it does not disable or uninstall it.

## The GUI will not open

Check that a graphical session is active. PySide6 needs system libraries in addition to its Python
wheel. Use the error's missing-library name and your distribution's Qt documentation to identify
what is needed. On supported x86-64 Linux, Qt can use Wayland or XCB depending on the session/plugin.
See [Qt's Linux requirements](https://doc.qt.io/qt-6/linux-requirements.html).

For a plugin-loading error, inspect `QT_QPA_PLATFORM` before forcing a backend. A previous
`offscreen` testing setting hides windows. `QT_DEBUG_PLUGINS=1 uvx tabletkey gui` provides diagnostics;
review them before sharing because they can include local paths.

## evdev fails to build during installation

Install your distribution's C compiler/build tools and Python development headers, or select
uv-managed Python with `uvx --python 3.12 tabletkey`. A compiler may still be required.
The repository's `uv sync --locked --managed-python` uses a managed Python with headers.
A failure before installation is complete is different from a runtime uinput permission failure.

## The app runs, but the pen does not move

Check **Enable tablet output**, the pen-enabled checkbox, and the selected connected monitor.
Then inspect `daemon status` for an output error. `cosmic-randr list` must report enabled displays.
The pen-routing implementation currently targets COSMIC; other Wayland compositors are unverified.

For startup errors, stop the background process and run in the terminal:

```sh
uvx tabletkey daemon stop
uvx tabletkey daemon run
```

Ctrl+C releases input and stops. Avoid starting a second driver while diagnosing the first.

## The wrong key lights up, or the wheel feels backwards

Use **Match the four keys to the picture** and press them starting nearest the dial.
Use **Identify wheel directions**, or **Reverse scrolling** to swap actions. Save afterwards.
Physical layout metadata changes labels/positions without changing existing hardware bindings.

## Pressure is too firm, or hover flickers

Try **Light touch** or comfortable-peak calibration in Pressure. Do not press harder to reach 100%.
In Pen detection, compare range-exit and timeout counters while reproducing a dropout.
Detection does not measure physical height or signal intensity. No hover smoothing is enabled;
a flickering cursor alone does not prove USB latency or a particular hardware fault.

## Reporting a useful issue

Include the tablet's USB identity, Linux distribution, COSMIC version, Python version, installation
method, `doctor` output, and steps to reproduce. State whether the same problem happens with other
drivers stopped. Remove personal paths if desired. Do not attach unrelated input or Windows installers.

For deliberate target-only raw recording, use a new local file:

```sh
mkdir -p captures
uvx tabletkey record --label hover-range --seconds 15 --output captures/hover-range.jsonl
uvx tabletkey inspect captures/hover-range.jsonl
```

Recording is read-only: it does not initialise the tablet. Raw output can differ when the device
has not already been initialised. Existing capture files are never overwritten.
