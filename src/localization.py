#!/usr/bin/env python3
"""
HOI4 Localization Reader
Reads localization files from Hearts of Iron IV installation
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class HOI4Localizer:
    def __init__(self, hoi4_path: str = r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV",
                 user_data_path: Optional[str] = None):
        self.hoi4_path = Path(hoi4_path)
        self.game_localization_path = self.hoi4_path / "localisation" / "english"

        # HOI4 user-data dir holds the launcher DB and resolved mod playsets.
        # Env override wins, then explicit arg, then the default Documents location.
        env_user = os.environ.get("HOI4_USER_DIR")
        if env_user:
            self.user_data_path = Path(env_user)
        elif user_data_path:
            self.user_data_path = Path(user_data_path)
        else:
            self.user_data_path = (
                Path.home() / "Documents" / "Paradox Interactive" / "Hearts of Iron IV"
            )

        self.translations: Dict[str, str] = {}
        self.loaded_files = set()
        # Populated by load_all_files(): the enabled mods of the active playset,
        # in game load order, as (display_name, localisation_dir) pairs.
        self.active_mods: List[Tuple[str, Path]] = []
    
    def load_localization_file(self, filename: str) -> int:
        """Load a single base-game localization file by name.

        Kept for callers that load specific files. The full mod-aware merge lives
        in load_all_files().
        """
        if filename in self.loaded_files:
            return 0

        file_path = self.game_localization_path / filename
        if not file_path.exists():
            print(f"Warning: Localization file not found: {filename}")
            return 0

        return self._load_file_path(file_path)

    def _load_file_path(self, file_path: Path) -> int:
        """Parse one .yml at an absolute path and merge its keys (last-writer-wins)."""
        key = str(file_path)
        if key in self.loaded_files:
            return 0

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()

            count = 0
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or line == 'l_english:':
                    continue

                # Pattern 1: key:version "value" (e.g., GER:0 "Germany")
                match = re.match(r'^\s*([^:]+?):\d+\s+"([^"]*)"', line)
                if not match:
                    # Pattern 2: key: "value" (e.g., AUS_political_events.16.t: "...")
                    match = re.match(r'^\s*([^:]+?):\s+"([^"]*)"', line)

                if match:
                    k = match.group(1).strip()
                    v = match.group(2).strip()
                    if k and v:
                        self.translations[k] = v
                        count += 1

            self.loaded_files.add(key)
            return count

        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            self.loaded_files.add(key)

        return 0

    def resolve_active_playset_mods(self) -> List[Tuple[str, Path]]:
        """Read the launcher DB for the active playset's enabled mods, in load order.

        Returns a list of (display_name, localisation_dir) for each enabled mod
        that ships a localisation folder, ordered by the playset's load position
        (earlier = lower priority, overridden by later mods). Returns [] if the
        DB is missing or unreadable so callers can fall back to base-game only.
        """
        db_path = self.user_data_path / "launcher-v2.sqlite"
        if not db_path.exists():
            print(f"Launcher DB not found at {db_path} - using base game locale only")
            return []

        mods: List[Tuple[str, Path]] = []
        try:
            # Read-only URI connection so we never disturb the launcher's DB.
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                active = conn.execute(
                    "SELECT id, name FROM playsets WHERE isActive=1"
                ).fetchone()
                if not active:
                    print("No active playset in launcher DB")
                    return []
                playset_id, playset_name = active
                rows = conn.execute(
                    """SELECT m.displayName, m.dirPath
                       FROM playsets_mods pm JOIN mods m ON m.id = pm.modId
                       WHERE pm.playsetId = ? AND pm.enabled = 1
                       ORDER BY pm.position""",
                    (playset_id,),
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f"Could not read launcher DB: {e} - using base game locale only")
            return []

        for display_name, dir_path in rows:
            if not dir_path:
                continue
            loc_dir = Path(dir_path) / "localisation"
            if loc_dir.is_dir():
                mods.append((display_name or Path(dir_path).name, loc_dir))

        print(f"Active playset '{playset_name}': {len(mods)} enabled mods ship localisation")
        return mods

    def _load_dir_recursive(self, directory: Path) -> int:
        """Merge every *_l_english.yml under a directory tree (last-writer-wins)."""
        loaded = 0
        for file_path in sorted(directory.rglob("*_l_english.yml")):
            loaded += self._load_file_path(file_path)
        return loaded

    def load_all_files(self):
        """Load all localization in game-accurate order: base game -> enabled mods
        (by playset load order). Later sources override earlier ones key-by-key,
        matching how HOI4 resolves a mod stack."""
        total_loaded = 0

        # 1. Base game (lowest priority).
        if self.game_localization_path.exists():
            n = self._load_dir_recursive(self.game_localization_path)
            print(f"Base game: {n} translations")
            total_loaded += n
        else:
            print(f"Base game localisation not found at {self.game_localization_path}")

        # 2. Enabled mods, in load order — later positions override earlier.
        self.active_mods = self.resolve_active_playset_mods()
        for display_name, loc_dir in self.active_mods:
            n = self._load_dir_recursive(loc_dir)
            if n:
                print(f"Mod '{display_name}': {n} translations")
                total_loaded += n

        print(f"Total translations in table: {len(self.translations)} "
              f"({total_loaded} reads across all sources)")
        return total_loaded
    
    def get_localized_text(self, key: str) -> str:
        """Get localized text for a key, return key if not found"""
        if key in self.translations:
            result = self.translations[key]
            
            # Handle $variable$ references (e.g., "$leon_blum$" -> "Léon Blum")
            if result.startswith('$') and result.endswith('$') and len(result) > 2:
                referenced_key = result[1:-1]  # Remove $ symbols
                if referenced_key in self.translations:
                    return self.translations[referenced_key]
                # Try variations of the referenced key
                for variant in [referenced_key.lower(), referenced_key.upper()]:
                    if variant in self.translations:
                        return self.translations[variant]
                # If reference not found, return the cleaned referenced key
                return self._clean_key_for_display(referenced_key)
            
            return result
        
        # Try variations
        variations = [key.lower(), key.upper()]
        for variant in variations:
            if variant in self.translations:
                result = self.translations[variant]
                # Handle $variable$ references in variations too
                if result.startswith('$') and result.endswith('$') and len(result) > 2:
                    referenced_key = result[1:-1]
                    if referenced_key in self.translations:
                        return self.translations[referenced_key]
                    return self._clean_key_for_display(referenced_key)
                return result
        
        # If not found, return a cleaned version
        return self._clean_key_for_display(key)
    
    def _clean_key_for_display(self, key: str) -> str:
        """Convert a game key to a readable format if no translation found"""
        cleaned = key
        cleaned = re.sub(r'^[A-Z]+_', '', cleaned)
        cleaned = re.sub(r'\.d$', '', cleaned)
        cleaned = re.sub(r'_events\.\d+$', '', cleaned)
        cleaned = cleaned.replace('_', ' ').title()
        return cleaned
    
    def get_country_name(self, tag: str, ideology: str = None) -> str:
        """Get country name from tag, optionally with ideological variant"""
        # Try ideological name first if ideology is provided
        if ideology:
            ideological_key = f"{tag}_{ideology}"
            if ideological_key in self.translations:
                return self.translations[ideological_key]

        # Try generic country name
        if tag in self.translations:
            return self.translations[tag]

        patterns = [f"{tag}_NAME", f"{tag}_DEF", f"{tag}_ADJ"]
        for pattern in patterns:
            if pattern in self.translations:
                return self.translations[pattern]

        return self._clean_key_for_display(tag)

    def get_country_display_name(
        self,
        tag: str,
        cosmetic_tag: Optional[str] = None,
        ruling_party: Optional[str] = None,
    ) -> str:
        """Resolve a country's currently-displayed name from save-state hints.

        HOI4 (especially mods like Kaiserredux) stores country names along
        two runtime axes:
        - `cosmetic_tag` — a save-time override identifying which name set
          is active (e.g. WHR's cosmetic_tag=WHR_BEL means look up the
          "Belarus" name family, not the bare WHR keys).
        - `ruling_party` — selects an ideology-specific variant within a
          name set (e.g. WHR_BEL_syndicalist_DEF vs WHR_BEL_market_liberal_DEF).

        Lookup order, most specific to least:
          1. <cosmetic>_<party>_DEF
          2. <cosmetic>_DEF
          3. <tag>_<party>_DEF
          4. <tag>_DEF / <tag> / <tag>_NAME
          5. any <tag>_*_DEF (alphabetical first) so dynamic-only tags
             surface SOMETHING readable instead of a cleaned-key fallback.
          6. _clean_key_for_display(tag) — last resort.

        Returns the `_DEF` ("definite article") form when available; this is
        what you'd say in a list ("the Baltic Federation", "the Russian
        Empire"). Strip the leading "the " yourself if you need a noun-phrase.
        """
        candidates = []
        if cosmetic_tag and ruling_party:
            candidates.append(f"{cosmetic_tag}_{ruling_party}_DEF")
        if cosmetic_tag:
            candidates.append(f"{cosmetic_tag}_DEF")
        if ruling_party:
            candidates.append(f"{tag}_{ruling_party}_DEF")
        candidates += [f"{tag}_DEF", tag, f"{tag}_NAME", f"{tag}_ADJ"]
        for key in candidates:
            value = self.translations.get(key)
            if value:
                return value

        # Last-ditch fallback: scan for any <tag>_<sub>_DEF. This catches
        # dynamic-only tags like BAT which have no plain key but ship dozens
        # of `BAT_FED_*_DEF` / `BAT_PRI_*_DEF` / etc. We pick the first
        # alphabetically — arbitrary but deterministic, and far more useful
        # than a cleaned-key like "Bat".
        prefix = f"{tag}_"
        for key in sorted(self.translations):
            if key.startswith(prefix) and key.endswith("_DEF"):
                value = self.translations[key]
                if value:
                    return value

        return self._clean_key_for_display(tag)
    
    def get_event_name(self, event_id: str) -> str:
        """Get event name/description"""
        # Try direct lookup
        if event_id in self.translations:
            return self.translations[event_id]
        
        # Try with .t suffix (title)
        title_key = f"{event_id}.t"
        if title_key in self.translations:
            return self.translations[title_key]
        
        # If no localization found, return original ID (for hidden events)
        return event_id
    
    def get_idea_name(self, idea_id: str) -> str:
        """Get national idea name"""
        return self.get_localized_text(idea_id)

    def get_idea_display(self, idea_id: str) -> Dict[str, object]:
        """Resolve a national idea's display info from the locale table.

        Returns ``{'name', 'description', 'is_hidden'}`` where:

        - ``name``: display name. Falls back to the level-stripped variant
          (``WRA_german_support_1`` -> looks up ``WRA_german_support``)
          when the exact key is missing; KR levels share base locale for
          many ideas. Empty string when no name resolves at all.
        - ``description``: ``<id>_desc`` (or its level-stripped variant).
          Empty string when missing — descriptions are often genuinely
          absent for scripted ideas.
        - ``is_hidden``: True when the idea is internal/UI-hidden. We
          flag ideas whose ID ends in ``_hidden`` or which have no
          resolvable name AND no level-stripped fallback. Match these
          to what the player doesn't see in-game.
        """
        # Try the exact key, then a level-stripped variant.
        candidates = [idea_id]
        stripped = re.sub(r"_\d+$", "", idea_id)
        if stripped != idea_id:
            candidates.append(stripped)

        name = ""
        desc = ""
        for key in candidates:
            if not name and key in self.translations:
                name = self.translations[key]
            desc_key = f"{key}_desc"
            if not desc and desc_key in self.translations:
                desc = self.translations[desc_key]
            if name and desc:
                break

        is_hidden = idea_id.endswith("_hidden") or not name
        return {
            "name": name,
            "name_clean": self._clean_display_string(name),
            "description": desc,
            "is_hidden": is_hidden,
        }

    def get_focus_description(self, focus_id: str) -> str:
        """Return the localized description for a national focus.

        HOI4 convention: `<focus_id>` holds the title, `<focus_id>_desc` holds
        the body text. Returns an empty string when no description exists,
        rather than a cleaned-key fallback (a missing description is normal
        and should not surface as 'Some Focus Desc')."""
        desc_key = f"{focus_id}_desc"
        return self.translations.get(desc_key, "")

    @staticmethod
    def _clean_display_string(value: str) -> str:
        """Strip HOI4 inline formatting from a string for single-line display.

        Removes ``§X`` color/style codes and truncates at the first ``\\n``
        (or literal ``\\n`` sequence stored in the yml). KR's party names
        often store ``Native Name\\n§LEnglish Translation§!`` — for a CLI
        row, only the first line is useful.
        """
        if not value:
            return value
        # Locale files store newlines as the two-character escape "\n", not as
        # an actual newline byte. Cut at either.
        for sep in ("\\n", "\n"):
            idx = value.find(sep)
            if idx >= 0:
                value = value[:idx]
                break
        # Strip color/style codes like §L ... §! and bare §X.
        value = re.sub(r"§.", "", value)
        return value.strip()

    def get_party_names(self, tag: str, party_id: str) -> Dict[str, str]:
        """Return the localized name forms for a country's political party.

        Returns ``{'short', 'long_raw', 'long_clean'}``:
        - ``short``: abbreviation key ``<TAG>_<party_id>_party``
          (e.g. ``CAN_national_populist_party`` -> "IUP").
        - ``long_raw``: full key ``<TAG>_<party_id>_party_long``, unmodified.
        - ``long_clean``: long_raw with HOI4 formatting stripped and
          truncated at the first ``\\n`` for single-line display.

        Any missing key returns an empty string. Callers that want the
        raw key resolved through ``$var$`` references should use
        ``get_localized_text`` directly.
        """
        short = self.get_localized_text(f"{tag}_{party_id}_party")
        long_raw = self.get_localized_text(f"{tag}_{party_id}_party_long")
        # get_localized_text falls back to a cleaned key when missing; that
        # noise is unhelpful here, so suppress it when the key is absent.
        if f"{tag}_{party_id}_party" not in self.translations:
            short = ""
        if f"{tag}_{party_id}_party_long" not in self.translations:
            long_raw = ""
        return {
            "short": short,
            "long_raw": long_raw,
            "long_clean": self._clean_display_string(long_raw),
        }