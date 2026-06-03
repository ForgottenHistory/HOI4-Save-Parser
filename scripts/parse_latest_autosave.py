#!/usr/bin/env python3
"""
Parse Latest HOI4 Autosave
Finds the most recent autosave in the HOI4 saves directory and parses it
"""

import os
import glob
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def find_hoi4_saves_directory():
    """Find the HOI4 saves directory"""
    # Common locations for HOI4 saves
    possible_paths = [
        os.path.expanduser("~/Documents/Paradox Interactive/Hearts of Iron IV/save games"),
        os.path.expanduser("~/Documents/Paradox Interactive/Hearts of Iron IV/save_games"),
        "C:/Users/" + os.getlogin() + "/Documents/Paradox Interactive/Hearts of Iron IV/save games",
        "C:/Users/" + os.getlogin() + "/Documents/Paradox Interactive/Hearts of Iron IV/save_games",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"[FOUND] HOI4 saves directory: {path}")
            return path
    
    print("[ERROR] Could not find HOI4 saves directory!")
    print("Please check that Hearts of Iron IV is installed and you have save games.")
    return None

def find_latest_autosave(saves_dir):
    """Find the most recent autosave file"""
    # Look for autosave files
    autosave_patterns = [
        os.path.join(saves_dir, "autosave*.hoi4"),
        os.path.join(saves_dir, "Autosave*.hoi4"),
        os.path.join(saves_dir, "*.hoi4")  # Fallback to any .hoi4 file
    ]
    
    latest_file = None
    latest_time = 0
    
    for pattern in autosave_patterns:
        files = glob.glob(pattern)
        for file_path in files:
            try:
                # Get file modification time
                mod_time = os.path.getmtime(file_path)
                if mod_time > latest_time:
                    latest_time = mod_time
                    latest_file = file_path
            except OSError:
                continue
    
    if latest_file:
        mod_datetime = datetime.fromtimestamp(latest_time)
        print(f"[FOUND] Latest autosave: {os.path.basename(latest_file)}")
        print(f"[INFO] Modified: {mod_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        return latest_file
    else:
        print("[ERROR] No autosave files found!")
        return None

def parse_save_file(save_path, output_path):
    """Parse the save file using the Rust parser"""
    parser_path = Path(__file__).parent.parent / "hoi4_parser" / "target" / "release" / "hoi4_parser.exe"
    
    if not parser_path.exists():
        print(f"[ERROR] Parser not found at: {parser_path}")
        print("Please build the parser first with: cd hoi4_parser && cargo build --release")
        return False
    
    print(f"[PARSING] Running parser on: {os.path.basename(save_path)}")
    
    try:
        # Run the parser with the save file path and output path
        result = subprocess.run([
            str(parser_path),
            save_path,
            output_path
        ], capture_output=True, text=True, encoding='utf-8', errors='ignore', cwd=parser_path.parent)
        
        if result.returncode == 0:
            print("[SUCCESS] Save file parsed successfully!")
            if result.stdout:
                print("Output lines:")
                for line in result.stdout.strip().split('\n')[-10:]:  # Show last 10 lines
                    if line.strip():
                        print(f"  {line}")
            return True
        else:
            print(f"[ERROR] Parser failed with return code: {result.returncode}")
            if result.stderr:
                print("Error output:")
                for line in result.stderr.strip().split('\n'):
                    if line.strip():
                        print(f"  {line}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to run parser: {e}")
        return False

def main():
    """Main function"""
    print("=" * 60)
    print("HOI4 AUTOSAVE PARSER FOR LIVE GAMEPLAY")
    print("=" * 60)
    
    # Find HOI4 saves directory
    saves_dir = find_hoi4_saves_directory()
    if not saves_dir:
        return False
    
    # Find latest autosave
    latest_save = find_latest_autosave(saves_dir)
    if not latest_save:
        return False
    
    # Set output path
    output_path = Path(__file__).parent.parent / "data" / "game_data.json"
    output_path.parent.mkdir(exist_ok=True)
    
    print(f"[OUTPUT] Will save to: {output_path}")
    
    # Parse the save file
    success = parse_save_file(latest_save, str(output_path))
    
    if success:
        print("\n" + "=" * 60)
        print("[SUCCESS] Game data updated successfully!")
        print("You can now use the Twitter stream with live game data.")
        print("=" * 60)
        return True
    else:
        print("\n" + "=" * 60)
        print("[FAILED] Could not parse the save file.")
        print("Check the error messages above.")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)