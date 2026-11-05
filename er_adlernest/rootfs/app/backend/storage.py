"""Storage source management for HA-mounted folders and app-owned CIFS mounts."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger("adlernest.storage")

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
STORAGE_FILE = DATA_DIR / "storage.json"
MOUNTS_DIR = DATA_DIR / "mounts"
CREDS_DIR = DATA_DIR / "credentials"
LOCAL_ROOTS = (Path("/media"), Path("/share"))
SMB_ID_RE = re.compile(r"^[a-f0-9-]{8,64}$")


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (MOUNTS_DIR, CREDS_DIR):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)


def _load() -> list[dict[str, Any]]:
    _ensure_dirs()
    if not STORAGE_FILE.exists():
        return []
    try:
        with STORAGE_FILE.open(encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, list) else []
    except (OSError, ValueError) as exc:
        logger.error("Could not load storage definitions: %s", exc)
        return []


def _save(items: list[dict[str, Any]]) -> None:
    _ensure_dirs()
    fd, temporary = tempfile.mkstemp(prefix="storage-", dir=DATA_DIR, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(items, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, STORAGE_FILE)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _mount_path(storage_id: str) -> Path:
    if not SMB_ID_RE.fullmatch(storage_id):
        raise ValueError("Invalid storage id")
    return MOUNTS_DIR / storage_id


def _credential_path(storage_id: str) -> Path:
    if not SMB_ID_RE.fullmatch(storage_id):
        raise ValueError("Invalid storage id")
    return CREDS_DIR / f"{storage_id}.cred"


def allowed_roots() -> tuple[Path, ...]:
    roots = [root for root in LOCAL_ROOTS if root.exists() and root.is_dir()]
    for item in _load():
        if item.get("type") == "smb":
            mount = _mount_path(str(item.get("id", "")))
            if os.path.ismount(mount):
                roots.append(mount)
    return tuple(roots)


def resolve_allowed_directory(value: str | os.PathLike[str], *, require_exists: bool = True) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Storage path must be absolute")
    candidate = Path(os.path.realpath(candidate))
    for root in allowed_roots():
        root = Path(os.path.realpath(root))
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if require_exists and (not candidate.exists() or not candidate.is_dir()):
            raise ValueError("Storage directory does not exist")
        return candidate
    raise ValueError("Path is outside an allowed storage root")


def source_status(item: dict[str, Any]) -> dict[str, Any]:
    mount = _mount_path(str(item["id"]))
    mounted = os.path.ismount(mount)
    return {
        **{key: value for key, value in item.items() if key != "password"},
        "mount_path": str(mount),
        "status": "connected" if mounted else "offline",
        "exists": mount.exists(),
    }


def list_sources() -> list[dict[str, Any]]:
    sources = [
        {"id": "media", "type": "local", "name": "Home Assistant media", "root": "/media", "status": "available" if Path("/media").is_dir() else "offline"},
        {"id": "share", "type": "local", "name": "Home Assistant share", "root": "/share", "status": "available" if Path("/share").is_dir() else "offline"},
    ]
    sources.extend(source_status(item) for item in _load())
    return sources


def _validate_server(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 253 or any(char in value for char in "\r\n/\\ "):
        raise ValueError("Invalid SMB server")
    return value


def _validate_share(value: str) -> str:
    value = value.strip().strip("/")
    if not value or len(value) > 255 or any(char in value for char in "\r\n") or ".." in value.split("/"):
        raise ValueError("Invalid SMB share")
    return value


def _write_credentials(storage_id: str, username: str, password: str, domain: str = "") -> Path:
    path = _credential_path(storage_id)
    content = f"username={username}\npassword={password}\n"
    if domain:
        content += f"domain={domain}\n"
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        handle.write(content)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return path


def upsert_source(payload: dict[str, Any]) -> dict[str, Any]:
    server = _validate_server(str(payload.get("server", "")))
    share = _validate_share(str(payload.get("share", "")))
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    domain = str(payload.get("domain", "")).strip()
    if not username or "\n" in username or "\n" in domain:
        raise ValueError("Invalid SMB credentials")
    storage_id = str(payload.get("id") or uuid4())
    _mount_path(storage_id)
    items = _load()
    cred_path = _credential_path(storage_id)
    if password:
        _write_credentials(storage_id, username, password, domain)
    elif not cred_path.exists():
        raise ValueError("Password is required for a new SMB source")
    item = {
        "id": storage_id,
        "type": "smb",
        "name": str(payload.get("name") or f"//{server}/{share}").strip()[:100],
        "server": server,
        "share": share,
        "username": username[:100],
        "domain": domain[:100],
    }
    items = [value for value in items if value.get("id") != storage_id]
    items.append(item)
    _save(items)
    return source_status(item)


def _find(storage_id: str) -> dict[str, Any]:
    item = next((value for value in _load() if value.get("id") == storage_id), None)
    if not item:
        raise KeyError("Storage source not found")
    return item


def mount_source(storage_id: str, *, timeout: int = 15) -> dict[str, Any]:
    item = _find(storage_id)
    mount = _mount_path(storage_id)
    mount.mkdir(parents=True, exist_ok=True)
    os.chmod(mount, 0o700)
    credentials = _credential_path(storage_id)
    if not credentials.exists():
        raise ValueError("Credentials file is missing")
    options = ["credentials=" + str(credentials), "vers=3.0", "ro", "nodev", "nosuid", "noexec"]
    target = f"//{item['server']}/{item['share']}"
    command = ["mount.cifs", target, str(mount), "-o", ",".join(options)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        logger.warning("SMB mount timed out for source %s", storage_id)
        return {**source_status(item), "status": "error", "error": "Mount timed out"}
    if result.returncode != 0 and not os.path.ismount(mount):
        logger.warning("SMB mount failed for source %s: %s", storage_id, result.stderr.strip()[:200])
        return {**source_status(item), "status": "error", "error": "Mount failed"}
    return source_status(item)


def test_source(payload: dict[str, Any]) -> dict[str, Any]:
    item = upsert_source(payload)
    return mount_source(str(item["id"]))


def unmount_source(storage_id: str) -> dict[str, Any]:
    item = _find(storage_id)
    mount = _mount_path(storage_id)
    if os.path.ismount(mount):
        result = subprocess.run(["umount", "--", str(mount)], capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0 and os.path.ismount(mount):
            raise RuntimeError("Unmount failed")
    return source_status(item)


def delete_source(storage_id: str) -> None:
    unmount_source(storage_id)
    items = [item for item in _load() if item.get("id") != storage_id]
    _save(items)
    try:
        _credential_path(storage_id).unlink()
        _mount_path(storage_id).rmdir()
    except FileNotFoundError:
        pass


def reconnect_all() -> None:
    for item in _load():
        try:
            mount_source(str(item["id"]))
        except Exception as exc:
            logger.warning("SMB reconnect failed for source %s: %s", item.get("id"), exc)
