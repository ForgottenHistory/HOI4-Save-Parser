"""Tests for src/save_locator.py."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from save_locator import (
    AUTOSAVE_FILENAME,
    default_saves_dir,
    find_autosave_path,
    read_signature,
)


class TestDefaultSavesDir:
    def test_env_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOI4_SAVES_DIR", str(tmp_path))
        assert default_saves_dir() == tmp_path

    def test_default_is_documents_subpath(self, monkeypatch):
        monkeypatch.delenv("HOI4_SAVES_DIR", raising=False)
        p = default_saves_dir()
        # We can't assert the literal home but the structure should hold.
        assert p.name == "save games"
        assert p.parent.name == "Hearts of Iron IV"


class TestFindAutosavePath:
    def test_appends_autosave_filename(self, tmp_path):
        path = find_autosave_path(tmp_path)
        assert path == tmp_path / AUTOSAVE_FILENAME

    def test_returns_path_even_if_file_missing(self, tmp_path):
        # Callers can stat or open the path themselves; we just compose it.
        path = find_autosave_path(tmp_path)
        assert not path.exists()
        # Still a Path, not None.
        assert isinstance(path, Path)


class TestReadSignature:
    def test_returns_mtime_and_size(self, tmp_path):
        f = tmp_path / "x.hoi4"
        f.write_text("hello")
        sig = read_signature(f)
        assert sig is not None
        mtime, size = sig
        assert size == 5
        assert isinstance(mtime, float)

    def test_returns_none_when_missing(self, tmp_path):
        assert read_signature(tmp_path / "missing.hoi4") is None

    def test_signature_changes_when_content_changes(self, tmp_path):
        f = tmp_path / "x.hoi4"
        f.write_text("hello")
        sig1 = read_signature(f)
        # Force a distinct mtime — os.utime is deterministic.
        os.utime(f, (sig1[0] + 1, sig1[0] + 1))
        f.write_text("hello world")  # different size too
        sig2 = read_signature(f)
        assert sig1 != sig2
