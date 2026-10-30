"""Read COSMIC output geometry and route only TabletKey's virtual pens."""

import fcntl
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
PREFIX = "TabletKey VO1060 Pen / "


@dataclass(frozen=True)
class Display:
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False

    @property
    def pen_name(self) -> str:
        return PREFIX + self.name

    def to_dict(self) -> dict:
        return asdict(self)


def parse_outputs(text: str) -> list[Display]:
    text = ANSI.sub("", text)
    blocks = re.split(r"(?m)^(?=\S+ \((?:enabled|disabled)\))", text)
    displays = []
    for block in blocks:
        head = re.match(r"(\S+) \(enabled\)", block)
        if head is None:
            continue
        position = re.search(r"Position:\s*(-?\d+),\s*(-?\d+)", block)
        scale = re.search(r"Scale:\s*([\d.]+)%", block)
        mode = re.search(r"(?m)^\s+(\d+)x(\d+)[^\n]*\(current\)", block)
        if position is None or scale is None or mode is None or float(scale[1]) <= 0:
            raise ValueError(f"Cannot determine active geometry for {head[1]}")
        width, height = int(mode[1]), int(mode[2])
        transform = re.search(r"Transform:\s*(\S+)", block)
        if transform and transform[1] in ("90", "270", "flipped-90", "flipped-270"):
            width, height = height, width
        displays.append(
            Display(
                head[1],
                int(position[1]),
                int(position[2]),
                max(1, round(width * 100 / float(scale[1]))),
                max(1, round(height * 100 / float(scale[1]))),
                "Xwayland primary: true" in block,
            )
        )
    if not displays:
        raise ValueError("COSMIC reported no enabled displays")
    return sorted(displays, key=lambda item: (not item.primary, item.name))


def detect_displays() -> list[Display]:
    try:
        result = subprocess.run(["cosmic-randr", "list"], capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError(f"Cannot query COSMIC displays with cosmic-randr: {exc}") from exc
    return parse_outputs(result.stdout)


def _separators(text: str, wanted: str) -> list[int]:
    """Find separators outside nested RON values, strings, and comments; fail closed."""
    result = []
    stack = []
    i = 0
    while i < len(text):
        char = text[i]
        if text.startswith("//", i):
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", i):
            depth = 1
            i += 2
            while i < len(text) and depth:
                if text.startswith("/*", i):
                    depth += 1
                    i += 2
                elif text.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise ValueError("Unclosed RON comment")
            continue
        raw = re.match(r'r(#{0,16})"', text[i:]) if char == "r" else None
        if raw:
            end = text.find('"' + raw[1], i + len(raw[0]))
            if end < 0:
                raise ValueError("Unclosed RON raw string")
            i = end + 1 + len(raw[1])
            continue
        if char in ('"', "'"):
            quote = char
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise ValueError("Unclosed RON string")
            continue
        if char in "({[":
            stack.append(char)
        elif char in ")}]":
            if not stack or stack.pop() != {")": "(", "}": "{", "]": "["}[char]:
                raise ValueError("Unbalanced RON value")
        elif char == wanted and not stack:
            result.append(i)
        i += 1
    if stack:
        raise ValueError("Unbalanced RON value")
    return result


def _strip_comments(text: str) -> str:
    # Used only on the key portion, never on values containing user strings.
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S).strip()


def route_config(text: str, displays: list[Display]) -> str:
    """Replace app-owned entries; every other entry remains byte-for-byte intact."""
    outer = text.strip()
    if not outer.startswith("{") or not outer.endswith("}"):
        raise ValueError("COSMIC input_devices must be a RON map; refusing to overwrite")
    body = outer[1:-1]
    _separators(body, ",")  # Validate before building any replacement.
    start = 0
    kept = []
    for end in [*_separators(body, ","), len(body)]:
        entry = body[start:end]
        start = end + 1
        if not _strip_comments(entry):
            if entry.strip():
                kept.append(entry)
            continue
        colons = _separators(entry, ":")
        if len(colons) != 1:
            raise ValueError("Cannot safely parse COSMIC device entry")
        try:
            key = json.loads(_strip_comments(entry[: colons[0]]))
        except ValueError as exc:
            raise ValueError("Cannot safely parse COSMIC device name") from exc
        if not isinstance(key, str):
            raise ValueError("COSMIC device names must be strings")
        if not key.startswith(PREFIX):
            kept.append(entry + ",")
    kept.extend(
        f"\n    {json.dumps(display.pen_name)}: (state: Enabled, map_to_output: Some({json.dumps(display.name)})),"
        for display in displays
    )
    return "{" + "".join(kept).rstrip() + "\n}\n"


def apply_routes(displays: list[Display], path: Path | None = None) -> None:
    if path is None:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        path = root / "cosmic/com.system76.CosmicComp/v1/input_devices"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name("input_devices.tabletkey.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = path.read_text(encoding="utf-8") if path.exists() else "{}\n"
        updated = route_config(original, displays)
        if updated == original:
            return
        backup = path.with_name("input_devices.tabletkey.bak")
        if path.exists() and not backup.exists():
            try:
                with backup.open("x", encoding="utf-8") as stream:
                    stream.write(original)
            except FileExistsError:
                pass
        fd, name = tempfile.mkstemp(prefix=".tabletkey-input-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            if path.exists() and path.read_text(encoding="utf-8") != original:
                raise OSError("COSMIC device settings changed concurrently; retrying without overwriting")
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
