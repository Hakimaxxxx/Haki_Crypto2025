#!/usr/bin/env python3
"""
Fix corrupted portfolio_history.json file
"""
import json
import os
import shutil

def fix_json_file(filename):
    """Try to fix corrupted JSON file"""
    if not os.path.exists(filename):
        print(f"File {filename} does not exist")
        return False
    
    # Backup original file
    backup_name = f"{filename}.corrupt_backup"
    shutil.copy2(filename, backup_name)
    print(f"Created backup: {backup_name}")
    
    try:
        # Try to load and see what's wrong
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"File size: {len(content)} characters")
        
        # Try to parse JSON
        try:
            data = json.loads(content)
            print(f"JSON is valid! Contains {len(data)} entries")
            return True
        except json.JSONDecodeError as e:
            print(f"JSON error at position {e.pos}: {e.msg}")
            
            # Try to truncate at error position and see if we can salvage some data
            error_pos = e.pos
            truncated_content = content[:error_pos]
            
            # Find last complete JSON object
            last_bracket = truncated_content.rfind('}')
            if last_bracket > 0:
                # Try to close the array properly
                salvaged_content = truncated_content[:last_bracket + 1]
                if salvaged_content.strip().endswith(','):
                    salvaged_content = salvaged_content.strip()[:-1]  # Remove trailing comma
                if not salvaged_content.strip().endswith(']'):
                    salvaged_content += ']'
                
                try:
                    salvaged_data = json.loads(salvaged_content)
                    print(f"Salvaged {len(salvaged_data)} entries from corrupted file")
                    
                    # Write salvaged data to new file
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(salvaged_data, f)
                    
                    print(f"Fixed file written with {len(salvaged_data)} entries")
                    return True
                except:
                    pass
            
            # If salvage fails, create empty array
            print("Could not salvage data, creating empty history file")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump([], f)
            return True
            
    except Exception as e:
        print(f"Error processing file: {e}")
        return False

if __name__ == "__main__":
    result = fix_json_file("portfolio_history.json")
    print(f"Fix result: {result}")