# HOI4 Save Parser

Tools for parsing Hearts of Iron IV save files and resolving localisation against a mod stack (Kaiserredux, sub-mods, etc.).

## What it does

- Parses plaintext `.hoi4` saves to structured JSON via a Rust extractor.
- Resolves text keys to display strings using the **active playset's** localisation, read directly from the HOI4 launcher database — so mods like Kaiserredux render correctly instead of falling back to vanilla.
- Standalone scripts on top of the above (e.g. list every completed national focus for a country).

Ironman (binary) saves are not supported — only plaintext.

## Layout

```
hoi4_parser/          Rust save -> JSON extractor
src/
  localization.py     KR-aware localizer (reads launcher-v2.sqlite for playset)
  game_data_loader.py Loads parsed game_data.json
scripts/
  parse_latest_autosave.py   Find newest autosave, run the Rust parser
  list_country_focuses.py    Dump completed focuses for a country tag
  save_cleaner.py            Strip bloat sections from a save in-place
data/                 Parsed JSON output (gitignored)
saves/                Source .hoi4 files (gitignored)
frontend/             SvelteKit viewer (separate stack)
```

## Prerequisites

- Hearts of Iron IV installed.
- Python 3.10+.
- Rust toolchain (only if rebuilding the parser).

## Usage

### Parse the latest autosave

```bash
python scripts/parse_latest_autosave.py
```

Writes `data/game_data.json`.

### List a country's completed focuses

```bash
python scripts/list_country_focuses.py saves/<save>.hoi4 CAN
```

Loads the launcher's active playset, merges every enabled mod's localisation in load order, and prints each focus ID alongside its display name.

### Live parsing loop

```bash
live_hoi4_parser.bat
```

Re-runs `parse_latest_autosave.py` every 5 minutes.

### Rebuild the Rust parser

```bash
cd hoi4_parser && cargo build --release
```

## Localisation resolution

`src/localization.py` resolves text in HOI4's actual load order:

1. Base game `localisation/english/`
2. Each enabled mod from the active playset, in `position` order — read from `~/Documents/Paradox Interactive/Hearts of Iron IV/launcher-v2.sqlite`. Last writer wins, matching how HOI4 itself resolves the stack.

If the launcher DB is missing or unreadable, the loader degrades gracefully to base-game-only.

Override the user-data location with `HOI4_USER_DIR` if your install isn't at the default Documents path.
