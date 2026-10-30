---
hide:
  - toc
---

<div class="tk-hero" markdown>

<div class="tk-eyebrow">VEIKK VO1060 · COSMIC · LINUX</div>

# Your tablet. Your shortcuts

Give your pen a comfortable touch, your wheel a purpose, and every button a job you remember.
TabletKey is a standalone Python driver with a visual settings app, built for one tablet and one
Linux desktop. No OpenTabletDriver installation required.

[Set up your tablet](getting-started.md){ .md-button .md-button--primary }
[Explore the controls](guide.md){ .md-button }

</div>

![TabletKey's controls editor](assets/screenshots/buttons.png)

<div class="grid cards" markdown>

- **Press it. See it. Map it.**

    Controls light up as you use them. Choose an action or record your shortcut.
    No hexadecimal guessing games.

- **Write with a lighter hand.**

    Try Light touch, inspect the response curve, and calibrate to a comfortable stroke.
    Raw and mapped pressure stay separate.

- **Keep your space.**

    Choose a display and drag the tablet's active area. Closing settings keeps the
    background driver—and your mappings—running.

- **Understand the signal.**

    See hover/contact and range exits on a detection timeline. No invented height
    estimate or signal-strength percentage.

</div>

## A small command, a useful window

After the first PyPI release:

```sh
uvx tabletkey setup --install  # explicit one-time Linux device permissions
uvx tabletkey                  # open settings, then click Start driver
```

**The first release is in preparation.** You can [run from source today](getting-started.md#from-source-available-now).
For regular use after publication, `uv tool install tabletkey` provides a persistent environment.

## Focused support, honest limits

TabletKey targets **VEIKK Voila VO1060, USB `2feb:000b`, on COSMIC Wayland**.
Standalone pen movement, wheel scrolling, comfortable pressure, and detection were physically confirmed
on the owner's device. Global mappings are implemented; per-app profiles and tilt output are not.
Other tablet models and other desktops are unverified. Hover smoothing is intentionally not enabled.

[What's verified](hardware.md){ .md-button }
[Get help](troubleshooting.md){ .md-button }

Independent project. Not affiliated with VEIKK. Original diagram and project code are MIT licensed.
