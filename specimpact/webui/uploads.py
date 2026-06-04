from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_FILES = 200
ALLOWED_EXTENSIONS = {
    "docs": {".md", ".txt"},
    "change": {".md"},
    "aliases": {".yml", ".yaml"},
    "openapi": {".yml", ".yaml", ".json"},
    "ddl": {".sql"},
    "table": {".csv", ".xlsx"},
    "review": {".json"},
    "eval": {".yml", ".yaml"},
}


def sanitize_filename(filename: str) -> str:
    if not filename or "\x00" in filename:
        raise ValueError("Upload filename is invalid")
    if PurePosixPath(filename).name != filename or PureWindowsPath(filename).name != filename:
        raise ValueError("Upload filename must be a basename")
    if filename in {".", ".."}:
        raise ValueError("Upload filename is invalid")
    return filename


def save_uploads(
    project_path: Path | str,
    workflow: str,
    files: list[tuple[str, bytes]],
) -> list[Path]:
    allowed = ALLOWED_EXTENSIONS.get(workflow)
    if not allowed:
        raise ValueError(f"Unknown upload workflow: {workflow}")
    if not files:
        raise ValueError("At least one upload file is required")
    if len(files) > MAX_FILES:
        raise ValueError(f"Upload submission exceeds {MAX_FILES} files")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(project_path) / ".specimpact" / "uploads" / f"{timestamp}-{uuid4().hex}"
    paths: list[Path] = []
    checked: list[tuple[str, bytes]] = []
    for filename, content in files:
        safe_name = sanitize_filename(filename)
        if Path(safe_name).suffix.lower() not in allowed:
            rendered = ", ".join(sorted(allowed))
            raise ValueError(f"{workflow} upload must use one of: {rendered}")
        if len(content) > MAX_FILE_SIZE:
            raise ValueError(f"Upload file exceeds {MAX_FILE_SIZE} bytes: {safe_name}")
        checked.append((safe_name, content))
    target.mkdir(parents=True, exist_ok=False)
    for safe_name, content in checked:
        path = target / safe_name
        path.write_bytes(content)
        paths.append(path)
    return paths
