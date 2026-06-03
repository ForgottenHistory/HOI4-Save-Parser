"""Shared fixtures for the test suite.

The fixtures here build small synthetic worlds on disk per-test (under tmp_path)
so nothing depends on the developer's local HOI4 install or launcher state.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ----------------------------------------------------------------------------
# YML helpers
# ----------------------------------------------------------------------------

def write_yml(path: Path, entries: dict[str, str], *, with_header: bool = True) -> Path:
    """Write a HOI4-style localisation .yml file. Values that already contain a
    leading ` "..."` are written verbatim, so tests can include version numbers
    or weird whitespace explicitly via `_RAW:` keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["l_english:"] if with_header else []
    for k, v in entries.items():
        if k.startswith("_RAW:"):
            lines.append(v)
        else:
            lines.append(f' {k}:0 "{v}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


# ----------------------------------------------------------------------------
# Launcher DB builder
# ----------------------------------------------------------------------------

def build_launcher_db(
    db_path: Path,
    *,
    active_playset: str | None,
    mods: list[dict],
) -> Path:
    """Create a minimal launcher-v2.sqlite with just the columns the localizer
    queries. `mods` is a list of dicts with keys: display_name, dir_path,
    enabled (bool), position (int), in_active_playset (bool)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE playsets (
                id TEXT PRIMARY KEY,
                name TEXT,
                isActive INTEGER
            );
            CREATE TABLE mods (
                id TEXT PRIMARY KEY,
                displayName TEXT,
                dirPath TEXT
            );
            CREATE TABLE playsets_mods (
                playsetId TEXT,
                modId TEXT,
                enabled INTEGER,
                position INTEGER
            );
            """
        )
        if active_playset:
            conn.execute(
                "INSERT INTO playsets VALUES (?, ?, ?)",
                ("ps_active", active_playset, 1),
            )
            # Also create an inactive playset to make sure we filter correctly.
            conn.execute(
                "INSERT INTO playsets VALUES (?, ?, ?)",
                ("ps_other", "Inactive Playset", 0),
            )
        for i, m in enumerate(mods):
            mod_id = f"mod_{i}"
            conn.execute(
                "INSERT INTO mods VALUES (?, ?, ?)",
                (mod_id, m["display_name"], str(m["dir_path"]) if m["dir_path"] else None),
            )
            if m.get("in_active_playset", True) and active_playset:
                conn.execute(
                    "INSERT INTO playsets_mods VALUES (?, ?, ?, ?)",
                    ("ps_active", mod_id, 1 if m["enabled"] else 0, m["position"]),
                )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ----------------------------------------------------------------------------
# Common fixtures
# ----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Ensure HOI4_USER_DIR from the developer's shell doesn't bleed into tests."""
    monkeypatch.delenv("HOI4_USER_DIR", raising=False)


@pytest.fixture
def hoi4_install(tmp_path: Path) -> Path:
    """An empty fake HOI4 install root. Tests that need a base game locale add
    files under `<root>/localisation/english/` themselves."""
    root = tmp_path / "hoi4_install"
    (root / "localisation" / "english").mkdir(parents=True)
    return root


@pytest.fixture
def user_dir(tmp_path: Path) -> Path:
    """An empty fake HOI4 user-data dir (where launcher-v2.sqlite lives)."""
    root = tmp_path / "hoi4_user"
    root.mkdir()
    return root


@pytest.fixture
def make_localizer(hoi4_install: Path, user_dir: Path):
    """Factory that returns a fresh HOI4Localizer pointed at the synthetic
    install + user-data dirs."""
    from localization import HOI4Localizer

    def _make() -> HOI4Localizer:
        return HOI4Localizer(
            hoi4_path=str(hoi4_install),
            user_data_path=str(user_dir),
        )

    return _make
