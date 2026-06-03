"""Smoke test confirming imports and fixtures wire up correctly."""

from pathlib import Path


def test_can_import_localizer():
    from localization import HOI4Localizer  # noqa: F401


def test_can_import_focus_extractor():
    from list_country_focuses import find_country_focus_block  # noqa: F401


def test_localizer_factory(make_localizer, hoi4_install, user_dir):
    loc = make_localizer()
    assert loc.hoi4_path == Path(hoi4_install)
    assert loc.user_data_path == Path(user_dir)
