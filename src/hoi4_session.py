"""Stateful session for streaming-style polling of a HOI4 autosave.

The use case: a daemon (stream overlay, chat bot, TTS, etc.) wants to
react to in-game state changes. Naively calling the extraction functions
each tick is wasteful because they re-read the 200MB save and re-parse
the whole character_manager every call.

``HOI4Session`` owns:
- the localizer (loaded once at startup),
- the most-recently-read save text,
- per-save caches for global parses (character names, country name hints)
  that every per-country query needs,
- per-tag caches for query results so repeated queries within one save
  are free.

The session signals freshness via ``refresh()``: it stats the autosave
path and, if the (mtime, size) signature changed, re-reads the file and
invalidates the caches. Returns True on change. Callers loop:

    session = HOI4Session()
    while True:
        if session.refresh():
            leader = session.country_leader("CAN")
            ...
        time.sleep(5)

The session doesn't poll on its own — the caller decides cadence. That
keeps watcher/debounce concerns in the streaming app rather than this
library.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from localization import HOI4Localizer
from map_data import get_country_neighbors, get_country_provinces
from save_locator import find_autosave_path, read_signature
from save_parsing import (
    get_game_date,
    get_player_tag,
    parse_character_names,
    parse_country_name_hints,
)


# Late imports for the script-layer composers; see _scripts_path() below.
# We deliberately don't import them at module load so importing
# hoi4_session.py doesn't require scripts/ to be on sys.path.

class HOI4Session:
    """Owns the localizer and the most-recently-read save state.

    Construction is cheap if ``load_localizer=False``; default is eager
    because the locale takes ~5s and for a streaming daemon you want that
    cost paid at startup, not on first save change.

    The ``save_path`` defaults to the rolling autosave; pass a custom path
    to point at a manual save instead.
    """

    def __init__(
        self,
        save_path: Optional[Path] = None,
        load_localizer: bool = True,
        hoi4_path: Optional[Path] = None,
    ):
        self.save_path: Path = save_path or find_autosave_path()
        self.hoi4_path = hoi4_path  # passed through to neighbors/provinces

        self.localizer: Optional[HOI4Localizer] = None
        if load_localizer:
            self._load_localizer()

        # Last-observed file signature; None until a successful refresh.
        self._signature: Optional[Tuple[float, int]] = None

        # Save-wide parses (invalidated on each refresh).
        self._save_text: Optional[str] = None
        self._characters: Optional[Dict[int, str]] = None
        self._hints: Optional[Dict[str, Dict[str, Optional[str]]]] = None

        # Per-tag query caches (invalidated on each refresh).
        self._cache_focuses: Dict[str, dict] = {}
        self._cache_parties: Dict[str, list] = {}
        self._cache_ideas: Dict[Tuple[str, bool], list] = {}
        self._cache_leader: Dict[str, Optional[dict]] = {}
        self._cache_neighbors: Dict[str, List[str]] = {}
        self._cache_provinces: Dict[str, Dict[int, set]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _load_localizer(self) -> None:
        """Load the KR-aware localizer. Suppresses its progress prints so
        a streaming daemon's logs aren't polluted; the caller can wrap
        construction to surface this."""
        loc = HOI4Localizer()
        with contextlib.redirect_stdout(io.StringIO()):
            loc.load_all_files()
        self.localizer = loc

    def ensure_localizer(self) -> HOI4Localizer:
        """Lazy localizer load for sessions constructed with load_localizer=False."""
        if self.localizer is None:
            self._load_localizer()
        return self.localizer  # type: ignore[return-value]

    @property
    def is_loaded(self) -> bool:
        """True once a save has been read at least once."""
        return self._save_text is not None

    @property
    def current_signature(self) -> Optional[Tuple[float, int]]:
        return self._signature

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Re-read the save if its (mtime, size) changed since last refresh.

        Returns True if anything changed (caller should re-run queries),
        False if the save is unchanged or missing.

        First call always returns True if the save exists, since the prior
        signature is None.
        """
        signature = read_signature(self.save_path)
        if signature is None:
            return False
        if signature == self._signature:
            return False

        # Read first, mutate state only after — if the read fails we
        # don't end up with an inconsistent session.
        save_text = self.save_path.read_text(encoding="utf-8", errors="ignore")

        self._save_text = save_text
        self._signature = signature
        self._characters = None
        self._hints = None
        self._cache_focuses.clear()
        self._cache_parties.clear()
        self._cache_ideas.clear()
        self._cache_leader.clear()
        self._cache_neighbors.clear()
        self._cache_provinces.clear()
        return True

    # ------------------------------------------------------------------
    # Lazy save-wide parses
    # ------------------------------------------------------------------

    @property
    def save_text(self) -> str:
        if self._save_text is None:
            raise RuntimeError(
                "No save loaded yet — call refresh() first (or check is_loaded)."
            )
        return self._save_text

    @property
    def characters(self) -> Dict[int, str]:
        """{character_id: name} — built once per save."""
        if self._characters is None:
            self._characters = parse_character_names(self.save_text)
        return self._characters

    @property
    def name_hints(self) -> Dict[str, Dict[str, Optional[str]]]:
        """{tag: {cosmetic_tag, ruling_party}} — built once per save."""
        if self._hints is None:
            self._hints = parse_country_name_hints(self.save_text)
        return self._hints

    @property
    def player_tag(self) -> Optional[str]:
        """The single-player country tag from the save header (None if absent).

        Doesn't need its own cache — get_player_tag is a single anchored
        regex on the loaded save text, microseconds even on a 200MB save.
        """
        return get_player_tag(self.save_text)

    @property
    def game_date(self) -> Optional[Dict[str, object]]:
        """The current in-game date as {year, month, day, hour, raw}, or None."""
        return get_game_date(self.save_text)

    # ------------------------------------------------------------------
    # Per-country queries with per-tag caching
    # ------------------------------------------------------------------

    def country_display_name(self, tag: str) -> str:
        h = self.name_hints.get(tag, {})
        return self.ensure_localizer().get_country_display_name(
            tag,
            cosmetic_tag=h.get("cosmetic_tag"),
            ruling_party=h.get("ruling_party"),
        )

    def country_focuses(self, tag: str) -> Optional[dict]:
        if tag not in self._cache_focuses:
            from list_country_focuses import get_country_focuses  # lazy import
            self._cache_focuses[tag] = get_country_focuses(
                self.save_text, tag, self.ensure_localizer()
            )
        return self._cache_focuses[tag]

    def country_parties(self, tag: str) -> Optional[list]:
        if tag not in self._cache_parties:
            from list_country_parties import get_country_parties
            self._cache_parties[tag] = get_country_parties(
                self.save_text, tag, self.ensure_localizer(),
                characters=self.characters,
            )
        return self._cache_parties[tag]

    def country_ideas(self, tag: str, include_hidden: bool = False) -> Optional[list]:
        key = (tag, include_hidden)
        if key not in self._cache_ideas:
            from list_country_ideas import get_country_ideas
            self._cache_ideas[key] = get_country_ideas(
                self.save_text, tag, self.ensure_localizer(),
                include_hidden=include_hidden,
            )
        return self._cache_ideas[key]

    def country_leader(self, tag: str) -> Optional[dict]:
        if tag not in self._cache_leader:
            from list_country_leader import get_country_leader
            self._cache_leader[tag] = get_country_leader(
                self.save_text, tag, self.ensure_localizer(),
                characters=self.characters,
                hints=self.name_hints,
                parties=self.country_parties(tag),
            )
        return self._cache_leader[tag]

    def country_neighbors(self, tag: str) -> List[str]:
        # This one is expensive (bitmap scan) so the cache really earns
        # its keep here. The map data itself doesn't depend on the save
        # but we still bind to this session for ergonomic reasons.
        if tag not in self._cache_neighbors:
            self._cache_neighbors[tag] = get_country_neighbors(
                self.save_text, tag, hoi4_path=self.hoi4_path,
            )
        return self._cache_neighbors[tag]

    def country_provinces(self, tag: str) -> Dict[int, set]:
        if tag not in self._cache_provinces:
            self._cache_provinces[tag] = get_country_provinces(
                self.save_text, tag, hoi4_path=self.hoi4_path,
            )
        return self._cache_provinces[tag]
