# HOI4 Save Parser

Pure-Python toolkit for extracting structured data from Hearts of Iron IV save files. Mod-stack-aware: works correctly with Kaiserredux and sub-mods by reading the HOI4 launcher's active playset and resolving map data + localisation in load order.

Ironman (binary) saves are not supported — only plaintext.

## Layout

```
src/
  localization.py     KR-aware localizer (reads launcher-v2.sqlite for playset)
  map_data.py         Mod-aware map data + province adjacency + neighbors
  save_parsing.py     Country-block + party + character + idea extractors
  save_locator.py     Find autosave path, detect changes
  hoi4_session.py     Cached session for streaming-style polling
scripts/
  list_country_focuses.py     Completed national focuses
  list_country_leader.py      Ruling party + current leader
  list_country_parties.py     All political parties with popularity
  list_country_ideas.py       Active national ideas
  list_country_neighbors.py   Land-bordering countries
  list_country_provinces.py   Owned states grouped by province
  save_cleaner.py             Strip bloat sections from a save in-place
saves/                Source .hoi4 files (gitignored)
tests/                pytest suite (~130 tests, hermetic)
```

## Prerequisites

- Hearts of Iron IV installed.
- Python 3.10+.
- Pillow + numpy (for the bitmap-adjacency scan used by `list_country_neighbors`).

## Usage

### As a library (streaming / repeated queries)

```python
from hoi4_session import HOI4Session
import time

session = HOI4Session()       # loads locale once (~1s)

while True:
    if session.refresh():     # ~0s when nothing changed
        leader   = session.country_leader("CAN")
        focuses  = session.country_focuses("CAN")
        ideas    = session.country_ideas("CAN")
        parties  = session.country_parties("CAN")
        neighbors = session.country_neighbors("CAN")
        # ... do something with the data
    time.sleep(5)
```

The session caches the localizer at startup, the save text + global parses (characters, name hints) once per refresh, and per-tag query results until the next refresh. A no-change refresh is a single `stat()` call.

### As one-off scripts

Each `scripts/list_country_*.py` script takes a save path and a 3-letter country tag:

```bash
python scripts/list_country_leader.py    saves/WRA_1936_07_19_01.hoi4 WRA
python scripts/list_country_focuses.py   saves/CAN_1946_05_28_24.hoi4 CAN
python scripts/list_country_parties.py   saves/WRA_1936_07_19_01.hoi4 WRA
python scripts/list_country_ideas.py     saves/CAN_1946_05_28_24.hoi4 CAN
python scripts/list_country_neighbors.py saves/WRA_1936_07_19_01.hoi4 WRA
python scripts/list_country_provinces.py saves/CAN_1946_05_28_24.hoi4 CAN --verbose
```

## How mod resolution works

Both localisation and map data (state files, `provinces.bmp`, `definition.csv`) are read in HOI4's actual load order:

1. Base game files in the install dir.
2. Each enabled mod from the active playset, in `position` order — read from `~/Documents/Paradox Interactive/Hearts of Iron IV/launcher-v2.sqlite`.
3. Later sources override earlier ones, matching how HOI4 itself resolves the stack.

For state files specifically, the unit of replacement is the **state ID**, not the filename — a mod redefining state 13 in `13-Estonia.txt` correctly displaces base game's `13-Karelia.txt`, even though the filenames don't match.

The launcher DB and saves dir are auto-detected; override via `HOI4_USER_DIR` and `HOI4_SAVES_DIR` env vars for non-standard installs.

If the launcher DB is missing or unreadable, the loader degrades gracefully to base-game-only.

## Tests

```bash
python -m pytest
```

~130 tests, all hermetic — they build synthetic mod trees, fake launcher SQLite DBs, and tiny synthetic saves in `tmp_path`. They don't depend on your actual HOI4 install or current playset, so they pass anywhere.
