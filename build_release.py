#!/usr/bin/env python3
import os
import zipfile
from pathlib import Path

def create_release():
    """Create release zip file for HACS."""
    base_dir = Path(__file__).parent
    component_dir = base_dir / "custom_components" / "neatsvor"
    output_file = base_dir / "neatsvor.zip"
    
    if not component_dir.exists():
        print("Error: neatsvor directory not found!")
        return
    
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in component_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(base_dir)
                zipf.write(file_path, arcname)
                print(f"Added: {arcname}")
    
    print(f"\nRelease zip created: {output_file} ({output_file.stat().st_size} bytes)")

if __name__ == "__main__":
    create_release()
