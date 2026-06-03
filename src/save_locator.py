"""Locate and detect changes to the HOI4 autosave.

HOI4 always writes the rolling autosave to a single well-known path:
``Documents/Paradox Interactive/Hearts of Iron IV/save games/autosave.hoi4``.
We don't have to search — we just point at that file and check whether its
(mtime, size) has moved since we last looked.

The ``HOI4_SAVES_DIR`` env var overrides the default Documents location for
non-standard installs or testing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple


AUTOSAVE_FILENAME = "autosave.hoi4"


def default_saves_dir() -> Path:
    """Where HOI4 writes saves on this machine."""
    env = os.environ.get("HOI4_SAVES_DIR")
    if env:
        return Path(env)
    return (
        Path.home()
        / "Documents"
        / "Paradox Interactive"
        / "Hearts of Iron IV"
        / "save games"
    )


def find_autosave_path(saves_dir: Optional[Path] = None) -> Path:
    """Return the path the game will rewrite on every autosave.

    Returns the path even if the file doesn't exist yet — callers can
    check ``path.exists()`` if they care, or ``read_signature(path)`` to
    handle both "missing" and "present" uniformly.
    """
    return (saves_dir or default_saves_dir()) / AUTOSAVE_FILENAME


def read_signature(path: Path) -> Optional[Tuple[float, int]]:
    """Return ``(mtime, size)`` for change detection, or None if missing.

    Comparing tuples is the cheapest reliable "did the autosave change?"
    check — much faster than re-reading the 200MB file just to discover
    it hasn't changed.

    Why both fields:
    - mtime alone misses the rare case of an in-place rewrite that happens
      to land on the same second (HOI4 doesn't typically do this, but
      filesystems with second-resolution mtimes make it a real risk
      during fast save cycles).
    - size alone misses changes that don't alter file length.
    """
    try:
        st = path.stat()
    except (FileNotFoundError, PermissionError):
        return None
    return (st.st_mtime, st.st_size)
