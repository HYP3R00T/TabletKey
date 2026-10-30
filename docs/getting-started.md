# Get your tablet ready

Welcome to TabletKey. Connect your **VEIKK Voila VO1060**, open the app, and make its controls your own.

## Desktop compatibility

TabletKey supports the **VEIKK Voila VO1060 (USB `2feb:000b`) on COSMIC Wayland**.
Pen and monitor mapping use COSMIC's desktop integration. Other Linux desktops and tablet models
are not currently supported. The [architecture guide](architecture.md#desktop-integration) explains
what broader desktop support would involve.

## Before you start

- Connect the tablet to the Linux desktop host, outside a container or sandbox.
- Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Use Python 3.12 or newer. uv can supply a managed Python.
- Have COSMIC's `cosmic-randr` command, udev, and the Linux uinput module available.
- Stop any competing tablet driver before starting TabletKey.

PySide6 Essentials provides the window; evdev provides virtual input. They are Python dependencies installed
with the package. On platforms without a matching evdev wheel, a C compiler and Python development
headers are needed. uv-managed Python includes its own headers. Qt may also require distribution
libraries—see [troubleshooting](troubleshooting.md) if the GUI cannot open.

## Open the app

With [uv installed](https://docs.astral.sh/uv/getting-started/installation/), run the one-time setup,
then open settings:

```sh
uvx tabletkey setup --install
uvx tabletkey
```

The command is lowercase `tabletkey`. The bare command opens settings, as does `uvx tabletkey gui`.
Connect the tablet and click **Start driver** to enable TabletKey.

For daily use, install the tool into a persistent environment:

```sh
uv tool install tabletkey
tabletkey
```

Use `tabletkey` instead of `uvx tabletkey` in the following examples when installed this way.
[uv explains the difference between running and installing tools](https://docs.astral.sh/uv/concepts/tools/).
The detached daemon uses the same Python environment that launched it: stop it before removing
that environment, clearing uv's cache, or upgrading the tool.

## From source

TabletKey is written in Python. To explore the code or make changes:

```sh
git clone https://github.com/HYP3R00T/TabletKey.git
cd TabletKey
uv sync --locked --managed-python
uv run tabletkey setup --install
uv run tabletkey
```

## What the one-time setup changes

`setup` without `--install` previews the rules. `setup --install` explicitly invokes sudo to:

1. Install `/etc/udev/rules.d/70-tabletkey.rules` for this tablet's hidraw/native input nodes and uinput.
2. Install `/etc/modules-load.d/tabletkey.conf` so uinput loads on boot, and load it now.
3. Reload udev rules and refresh access for the target tablet and uinput.

It does not install a login service, add you to the input group, grant other physical keyboard access,
or remove another tablet driver. Run TabletKey itself as your normal desktop user, not with sudo.
If access still fails, unplug/replug the tablet and run `uvx tabletkey doctor`.

## Set up your first profile

1. Click **Start driver**. Wait for the tablet to be connected and output ready.
2. In **Buttons & wheel**, press a physical key. Its control lights up and becomes selected.
3. Pick an action from the dropdown. Try Undo, Copy, or a custom shortcut.
4. In **Pen & display**, select the desired monitor. Leave the whole tablet selected to begin.
5. In **Pressure**, try Light touch if the linear response feels too firm.
6. Click **Save changes**. Changes to controls and pen options apply together.

The initial profile enables pen and wheel output. The five pressable controls start unassigned.
Physical wheel direction is not assumed: use **Identify wheel directions** to label it.

## Keep it running

Closing settings leaves the driver active. You can also start it directly:

```sh
uvx tabletkey daemon start
uvx tabletkey daemon status
uvx tabletkey daemon stop
```

Reconnects are handled while the daemon runs. A second start reports the existing process.
There is no automatic login startup. Use `daemon run` to keep it in the foreground instead.
