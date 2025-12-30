# HOI4 AI Addon

A toolkit for extracting and analyzing data from Hearts of Iron 4 save files, with AI-powered content generation capabilities.

## Overview

HOI4 AI Addon parses HOI4 binary save files and extracts structured game data. Includes additional "streaming-tools" that I used to test things in real time. Extracted data can be analyzed and used for AI-generated content like reports and commentary.

## Features

- **Save File Parsing** - Rust-based parser extracts data from `.hoi4` binary saves
- **Country Data Extraction** - Leaders, ideology, stability, war support, political power
- **Focus Tree Tracking** - Completed national focuses and progression
- **Character Extraction** - Country leaders, advisors, unit commanders
- **Localization Support** - Maps game IDs to readable names using HOI4's locale files
- **AI Content Generation** - Generate reports and analysis using extracted game data

## Tech Stack

- **Rust** - High-performance HOI4 save file parser (uses `hoi4save` crate)
- **Python** - Data analysis, localization, AI integrations
- **OpenRouter API** - AI model integration for content generation

## Project Structure

```
HOI4-AI-Addon/
├── hoi4_parser/           # Rust save file parser
│   ├── src/main.rs        # Core parsing logic
│   └── Cargo.toml
├── src/
│   ├── services/          # Data extraction services
│   ├── *_analyzer.py      # Game data analyzers
│   ├── localization.py    # HOI4 text localization
│   ├── game_data_loader.py
│   └── ai_client.py       # AI API integration
├── data/
│   ├── game_data.json     # Extracted game state
│   └── personas/          # AI persona templates
├── locale/                # HOI4 localization files
└── streamer-tools/        # Experimental streaming integrations
```

## Prerequisites

- Hearts of Iron 4 installed
- Python 3.7+
- Rust (to rebuild parser, optional)

## Usage

### Parse a Save File

```bash
python parse_latest_autosave.py
```

This finds your latest HOI4 autosave and extracts game data to `data/game_data.json`.

### Live Parsing

```bash
live_hoi4_parser.bat
```

Monitors for save file changes and automatically re-parses.

### Build Rust Parser

Only needed if modifying the parser:

```bash
cd hoi4_parser
cargo build --release
```

## Extracted Data

The parser outputs structured JSON containing:

- **Countries** - All nations with their current state
- **Leaders** - Country leaders and their traits
- **Political State** - Ruling party, ideology, stability, war support
- **National Focuses** - Completed focuses and dates
- **Military** - Unit counts, commanders
- **Diplomacy** - Factions, wars, relations

## Experimental: Streamer Tools

The `streamer-tools/` directory contains experimental integrations for streaming, including an AI Twitter feed generator and breaking news overlay. These are optional extras.

## License

For personal/educational use with Hearts of Iron 4.
