# TabletKey

Python/uv companion for the VEIKK VO1060 on Linux. Scope is this device, not a general tablet driver.

- Read README.md for runnable commands and current status; docs/hardware.md owns protocol evidence and the investigation plan.
- Keep confirmed hardware evidence separate from inferred decoding and proposed features.
- Preserve OTD pen functionality. Never silently send device initialization commands, change input permissions, or install services.
- Access only target USB 2feb:000b; never record unrelated keyboard input.
- Keep raw captures under ignored captures/. Do not commit captures or proprietary Windows binaries without explicit authorization.
- Validate changes with uv run pytest, uv run ruff check ., uv run ruff format --check ., and uv run ty check.
- No commits, pushes, publishing, or deployment without explicit user authorization.
