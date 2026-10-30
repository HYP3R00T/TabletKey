"""Private local daemon control. No PID-file signals or network listener."""

import json
import os
import socket
import stat
import struct
from pathlib import Path

MAX_MESSAGE = 65536


def runtime_dir() -> Path:
    root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/tabletkey-runtime-{os.getuid()}"))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root_info = root.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.getuid()
        or stat.S_IMODE(root_info.st_mode) != 0o700
    ):
        raise OSError(f"XDG runtime directory must be private and owned by this user: {root}")
    path = root / "tabletkey"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise OSError(f"Runtime directory must be a private directory owned by this user: {path}")
    return path


def receive(connection: socket.socket) -> dict:
    data = bytearray()
    while b"\n" not in data:
        chunk = connection.recv(4096)
        if not chunk:
            raise ConnectionError("Daemon connection closed before a complete message")
        data.extend(chunk)
        if len(data) > MAX_MESSAGE:
            raise ValueError("Daemon message too large")
    value = json.loads(bytes(data).split(b"\n", 1)[0])
    if not isinstance(value, dict):
        raise ValueError("Expected a daemon message object")
    return value


def send(connection: socket.socket, message: dict) -> None:
    connection.sendall(json.dumps(message).encode() + b"\n")


def request(command: str, **payload) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(0.8)
        client.connect(str(runtime_dir() / "daemon.sock"))
        _, uid, _ = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise OSError("Daemon user does not match this user")
        send(client, {"command": command, **payload})
        response = receive(client)
    if "error" in response:
        raise ValueError(response["error"])
    return response


def status() -> dict:
    try:
        return request("status")
    except (FileNotFoundError, ConnectionError):
        return {"running": False}
