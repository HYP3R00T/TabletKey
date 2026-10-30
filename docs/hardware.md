# VO1060 hardware evidence

## Device and Protocol

Target USB identity: `2feb:000b`. Local Linux sysfs exposes three hidraw interfaces.
Interface 2 has numbered report 9, a 12-byte input payload (13 bytes including ID), and an
8-byte output payload (9 bytes including ID), verified from the attached device's HID descriptor.

The upstream [VO1060 configuration](https://github.com/OpenTabletDriver/OpenTabletDriver/blob/0.6.x/OpenTabletDriver.Configurations/Configurations/VEIKK/VO1060.json)
provides initialization payloads `09 01 04` and `09 02 02`, plus coordinate limits 50800×31750
and pressure maximum 8191. TabletKey pads output reports to the descriptor's nine-byte length.
The upstream [pen parser](https://github.com/OpenTabletDriver/OpenTabletDriver/blob/0.6.x/OpenTabletDriver.Configurations/Parsers/Veikk/VeikkTabletReport.cs)
provides field layout evidence. The driver implementation was written independently; these references
establish protocol facts, not runtime dependencies.

The [official product image](https://veikk.com/products/voila-l) shows four mechanical keys,
a center button in the dial, and the rotating wheel.

## Captured Controls

The user recorded `otd-unmapped-retry.jsonl` after removing OTD's auxiliary mappings:

- 38 thirteen-byte reports, all from interface 2, with a complete session end marker.
- Five button press/release pairs, identifiers `08`, `04`, `02`, `01`, `10` in press order.
- Button prefix `09 42 01`; byte 3 alternates `01`/`00` for press/release.
- Wheel prefix `09 42 03`; byte 4 contains `02` or `01`, with active/release pulse pairs.
- Associating `10` with the center button remains an inference from the user's sequence.
- Physical wheel polarity has not been isolated; UI mappings can be swapped.

The user later confirmed that physical keys 1–4 match identifiers `01`, `02`, `04`, `08`,
in the order shown in the product image. The earlier mixed capture order did not establish physical
positions. The UI default now follows this confirmed order; saved custom calibrations and hardware
bindings are preserved.

Raw captures remain local under ignored `captures/` and are not committed.

## Standalone Verification — 2026-10-30

The first standalone attempt found permission denied on the target native input nodes.
OTD was restored after cleanup. The user then ran TabletKey's explicit udev setup command.
The subsequent test established:

- OTD was stopped; executable inspection confirmed it was not running.
- TabletKey's initialization writes succeeded on interface 2.
- All three hidraw interfaces opened, and three native VO1060 evdev nodes were grabbed.
- Virtual keyboard, mouse, and pressure-sensitive pen devices were created.
- COSMIC routing selected the enabled primary output HDMI-A-1 at logical 1920×1080, offset 1920,0.
- The user's existing native-device and OTD COSMIC routing entries were preserved.

TabletKey was then started as the real detached daemon with OTD stopped. The user was asked to
unplug/replug the tablet and test pen and wheel; the user reported **pen and scrolling work**.
Afterward, daemon status showed initialized/connected/pen-active, 2729 decoded pen reports out of
2794 total reports, and no device or output error. OTD remained stopped.
This establishes operation after a fresh connection without a running OTD daemon.

## Remaining Validation

Pressure decoding/output is implemented, but brush-width response in a pressure-aware drawing app
has not been specifically confirmed. Multi-monitor crossing, crop/rotation ergonomics, sustained
stationary contact, simultaneous controls, repeat behavior, and reboot/startup need further tests.
Tilt and per-app profiles are not implemented. No OTD uninstall or permanent service disable has occurred.

Raw diagnostics remain read-only. Standalone daemon startup is the explicit device-initializing,
native-input-grabbing path; do not confuse the guarantees of those two modes.
