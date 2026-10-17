from __future__ import annotations

import os
from pathlib import Path


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(0o700)


def open_private_file(path: Path):
    """Create a new upload file with owner-only permissions where the OS supports them."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "wb")
