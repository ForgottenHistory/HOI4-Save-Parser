import re
import os
from typing import List, Tuple

class SaveCleaner:
    def __init__(self):
        """Clean up HOI4 save files by removing large unnecessary sections"""
        self.sections_to_remove = [
            'provinces',
            'states', 
            'raids',
            'project_pool',
            'program',
            'technology',
            'equipment_market',
            'equipments',
            'division_templates',
            'strategic_operatives',
            'character_manager',
            'rail_way',
            'power_balance',
            'weather',
            'unit_leader',
            'strategic_air',
            'combat',
            'supply_system_2',
            'threat',
            'variables',
            'combat_log',
            'resources',
            'production',
            'dynamic_modifier',
            'intelligence_agency',
            'division_template_id',
            'division_names_tracker',
            'units',
            'cached_navy_strength',
            'navy_theater',
            'theatres',
            'fuel_status',
            'deployment',
            'diplomacy',
            'ai',
            'strategic_navy',
            'intel',
            'name_group',
            'program_status',
            'recruit_scientist',
            'ship_names_tracker',
            'operative_codenames_tracker',
            'railway_gun_names_tracker'
        ]
    
    def clean_save_file(self, input_path: str, output_path: str = None) -> bool:
        """
        Clean save file by removing specified sections
        Returns True if successful, False otherwise
        """
        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_cleaned{ext}"
        
        try:
            print(f"Reading save file: {input_path}")
            with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            original_size = len(content)
            original_lines = content.count('\n')
            print(f"Original file: {original_size:,} characters, {original_lines:,} lines")
            
            # Remove each section
            for section in self.sections_to_remove:
                before_size = len(content)
                content, removed_count = self._remove_section_robust(content, section)
                after_size = len(content)
                
                if removed_count > 0:
                    reduction = before_size - after_size
                    print(f"✓ Removed {removed_count} occurrence(s) of {section} ({reduction:,} chars)")
                else:
                    print(f"✗ Section not found: {section}")
            
            # Clean up excessive newlines
            content = self._cleanup_newlines(content)
            
            # Write cleaned file
            print(f"Writing cleaned file: {output_path}")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            new_size = len(content)
            new_lines = content.count('\n')
            reduction = original_size - new_size
            print(f"Cleaned file: {new_size:,} characters, {new_lines:,} lines")
            print(f"Total reduction: {reduction:,} characters ({reduction/original_size*100:.1f}%)")
            
            return True
            
        except Exception as e:
            print(f"Error cleaning save file: {e}")
            return False
    
    def _remove_section_robust(self, content: str, section_name: str) -> Tuple[str, int]:
        """
        Robust section removal that handles complex nesting and separate-line braces
        """
        # Find all potential section starts
        pattern = rf'^\s*{re.escape(section_name)}\s*=\s*'
        
        removed_count = 0
        lines = content.split('\n')
        sections_to_remove = []  # Store (start_line, end_line) pairs
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if re.match(pattern, line):
                print(f"  Found {section_name} starting at line {i+1}: {line.strip()}")
                
                # Check if opening brace is on same line or next line
                brace_count = line.count('{') - line.count('}')
                start_line = i
                
                # If no opening brace on this line, look for it on next lines
                search_line = i
                while brace_count == 0 and search_line + 1 < len(lines):
                    search_line += 1
                    next_line = lines[search_line].strip()
                    if next_line == '{':
                        brace_count = 1
                        break
                    elif '{' in next_line:
                        brace_count = next_line.count('{') - next_line.count('}')
                        break
                    elif next_line and not next_line.startswith('\t') and not next_line.startswith(' '):
                        # Hit a non-indented line that's not a brace, probably not our section
                        break
                
                if brace_count > 0:
                    # Found opening brace, now find the matching closing brace
                    current_line = search_line + 1
                    
                    while current_line < len(lines) and brace_count > 0:
                        line_content = lines[current_line]
                        brace_count += line_content.count('{') - line_content.count('}')
                        current_line += 1
                    
                    if brace_count == 0:
                        end_line = current_line - 1
                        sections_to_remove.append((start_line, end_line))
                        print(f"  -> Section spans lines {start_line+1} to {end_line+1} ({end_line-start_line+1} lines)")
                        removed_count += 1
                        i = end_line + 1  # Skip past this section
                        continue
                    else:
                        print(f"  -> Warning: Could not find closing brace for {section_name}")
            
            i += 1
        
        # Remove sections in reverse order to maintain line numbers
        for start_line, end_line in reversed(sections_to_remove):
            del lines[start_line:end_line+1]
        
        return '\n'.join(lines), removed_count
    
    def _cleanup_newlines(self, content: str) -> str:
        """Clean up excessive newlines while preserving structure"""
        print("Cleaning up excessive newlines...")
        
        # Replace multiple consecutive newlines with at most 2
        # This preserves section separation while removing huge gaps
        cleaned = re.sub(r'\n{3,}', '\n\n', content)
        
        # Remove trailing whitespace from lines
        lines = cleaned.split('\n')
        lines = [line.rstrip() for line in lines]
        
        return '\n'.join(lines)
    
    def preview_sections(self, save_path: str) -> None:
        """
        Preview what sections exist and their approximate sizes
        """
        try:
            print(f"Analyzing save file: {save_path}")
            print("=" * 50)
            
            with open(save_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            for section in self.sections_to_remove:
                size, count = self._get_section_info_robust(content, section)
                if size > 0:
                    if count > 1:
                        print(f"{section}: ~{size:,} characters ({count} occurrences)")
                    else:
                        print(f"{section}: ~{size:,} characters")
                else:
                    print(f"{section}: Not found")
                    
        except Exception as e:
            print(f"Error analyzing save file: {e}")
    
    def _get_section_info_robust(self, content: str, section_name: str) -> Tuple[int, int]:
        """Get section info using the same robust method as removal"""
        pattern = rf'^\s*{re.escape(section_name)}\s*=\s*'
        
        lines = content.split('\n')
        total_size = 0
        count = 0
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if re.match(pattern, line):
                count += 1
                start_line = i
                
                # Find opening brace (same logic as removal)
                brace_count = line.count('{') - line.count('}')
                search_line = i
                
                while brace_count == 0 and search_line + 1 < len(lines):
                    search_line += 1
                    next_line = lines[search_line].strip()
                    if next_line == '{':
                        brace_count = 1
                        break
                    elif '{' in next_line:
                        brace_count = next_line.count('{') - next_line.count('}')
                        break
                    elif next_line and not next_line.startswith('\t') and not next_line.startswith(' '):
                        break
                
                if brace_count > 0:
                    current_line = search_line + 1
                    
                    while current_line < len(lines) and brace_count > 0:
                        line_content = lines[current_line]
                        brace_count += line_content.count('{') - line_content.count('}')
                        current_line += 1
                    
                    if brace_count == 0:
                        end_line = current_line - 1
                        section_lines = lines[start_line:end_line+1]
                        section_size = len('\n'.join(section_lines))
                        total_size += section_size
                        i = end_line + 1
                        continue
            
            i += 1
        
        return total_size, count

# Example usage
if __name__ == "__main__":
    cleaner = SaveCleaner()
    
    # Example save file path - update this to your actual save file
    save_file = "autosave.hoi4"  # or whatever your save file is called
    
    # Preview what we'll remove
    cleaner.preview_sections(save_file)
    
    # Clean the save file
    success = cleaner.clean_save_file(save_file)
    
    if success:
        print("\nSave file cleaning completed successfully!")
    else:
        print("\nFailed to clean save file.")