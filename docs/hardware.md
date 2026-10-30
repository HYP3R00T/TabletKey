# VO1060 hardware investigation

## Confirmed starting points

- This project's target USB identity is `2feb:000b`.
- Local Linux sysfs lists three HID interfaces for the attached VO1060.
- Initial local OTD settings contained five auxiliary bindings mapped to `7`; the user subsequently removed those mappings.
- The upstream [VO1060 configuration](https://github.com/OpenTabletDriver/OpenTabletDriver/blob/0.6.x/OpenTabletDriver.Configurations/Configurations/VEIKK/VO1060.json)
  declares five auxiliary buttons and uses `VeikkReportParser`, with no wheel specification.
- The upstream [VEIKK parser](https://github.com/OpenTabletDriver/OpenTabletDriver/blob/0.6.x/OpenTabletDriver.Configurations/Parsers/Veikk/VeikkReportParser.cs)
  can dispatch some reports to a relative wheel parser. This is a lead, not proof that it decodes this device correctly.

These observations were made on 2026-10-30. Capture evidence must establish the actual format on this device.
No upstream code has been copied into this project.

## First acceptance check

1. Run `uv run tabletkey doctor` on the host. Confirm the target interfaces are accessible.
2. Record an idle baseline, each button press/release, and each wheel direction into separate labeled files.
3. Inspect each capture. Confirm the corresponding action produces repeatable changes.
4. Repeat with OTD running and, if necessary, stopped. Record that condition in the label.
5. Preserve the raw evidence before writing a decoder. Unknown reports must remain observable.

Capture files use JSON Lines: a versioned session header, timestamped raw reports with
interface paths, optional errors, and a final status. An absent end marker means the capture
is incomplete. Reports carry monotonic elapsed seconds; the header carries UTC wall time.
`inspect` shows varying byte offsets and common report patterns; it does not infer button identities.

## Local verification

A two-second read-only baseline on 2026-10-30 successfully opened all three host hidraw
interfaces while the existing OTD setup remained unchanged. It received zero reports.
This verifies access and cleanup only; no physical control was deliberately exercised,
and simultaneous event delivery has not been established. The local capture is ignored.

The initially evaluated HIDAPI wheel selected a libusb backend on this machine. TabletKey
instead opens Linux hidraw nodes directly with `O_RDONLY | O_NONBLOCK`, avoiding USB
interface claims and any backend driver-detachment behavior. No external runtime dependency
is needed for this Linux diagnostic slice.

## Control capture evidence

The user recorded `otd-unmapped-retry.jsonl` after removing the OTD auxiliary mappings.
It contains 38 thirteen-byte reports from interface 2 and a complete end marker.
The raw file remains local under ignored `captures/`.

- Five button press/release pairs appeared, with identifiers `08`, `04`, `02`, `01`, `10` in press order.
- Reports beginning `09 42 01` represented button activity; byte 3 alternated between `01` and `00`.
- Wheel activity appeared as `09 42 03` reports with byte 4 values `02` and `01`.
  The values interleave in the mixed capture, so clockwise/counterclockwise assignment is not established.
- The [official product page and image](https://veikk.com/products/voila-l) show four mechanical keys
  plus a center button within the rotating dial. This agrees with five distinct captured button identifiers.
- Associating `10` with the center button is still an inference from the user's sequence, not an isolated test.

Receiving these reports establishes raw control input, not system-wide output, pen coexistence under load,
or reconnect behavior. The remaining work below is still proposed.

## Proposed next slices

These are planned, not implemented or verified:

1. Decode verified button states and wheel deltas; test against reviewed captures.
2. Prove Linux uinput scrolling and key output alongside OTD, without duplicate events or lost pen pressure.
3. Add a PySide6 interface with live control highlighting and editable saved mappings.
4. Add reconnection, login startup, and unplug/replug/reboot tests.

Python remains the implementation language. OTD can continue handling the pen if coexistence
works. If sharing the HID interfaces loses reports, choose a single hardware reader with an
explicit event bridge, or reconsider ownership before adding more functionality.

If USB captures do not explain initialization or wheel mode, inspect the official Windows
package with [REA](https://github.com/morluto/rea) or capture its USB traffic. The installer EXE
may merely unpack the DLL or service that actually communicates with the tablet.
