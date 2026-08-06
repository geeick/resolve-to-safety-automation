"""
cleanup_resolve_to_safety_folder.py

Moves old/useless generated files into an archive folder.

Run this from:
    C:\Users\info\OneDrive\Desktop\Resolve to Safety Automation

Command:
    py cleanup_resolve_to_safety_folder.py

This does NOT delete files. It moves old versions into:
    archive_old_versions/
"""

from pathlib import Path
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "archive_old_versions"

KEEP_EXACT = {
    ".env",
    "README_Resolve_to_Safety_Automation.md",
    "location_merge_map_v3.csv",
    "location_merge_map_v2.csv",
    "create_shift_reports_from_resolve_v10.py",
    "create_shift_reports_from_resolve_v9.py",
    "shift_report_web_app_v23_pricing_suggestions.py",
    "price_consistency_page.py",
    "cleanup_resolve_to_safety_folder.py",
}

KEEP_DIRS = {
    "shift_report_downloads",
    "shift_report_outputs",
    "archive_old_versions",
}

def should_archive(path: Path) -> bool:
    if path.is_dir():
        return False

    if path.name in KEEP_EXACT:
        return False

    if path.name.startswith("create_shift_reports_from_resolve") and path.suffix == ".py":
        return True

    if path.name.startswith("shift_report_web_app") and path.suffix == ".py":
        return True

    if path.name == "location_merge_map.csv":
        return True

    # Old test CSVs in root are safer to archive manually, so do not auto-move them.
    return False

def main():
    ARCHIVE.mkdir(exist_ok=True)

    moved = []

    for path in ROOT.iterdir():
        if path.name in KEEP_DIRS:
            continue

        if should_archive(path):
            dest = ARCHIVE / path.name

            if dest.exists():
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = ARCHIVE / f"{path.stem}_{stamp}{path.suffix}"

            shutil.move(str(path), str(dest))
            moved.append((path.name, dest.name))

    print("Cleanup complete.")
    print(f"Archived {len(moved)} files.")

    if moved:
        print("\nMoved files:")
        for old, new in moved:
            print(f"  {old} -> archive_old_versions/{new}")

    print("\nKept files:")
    for name in sorted(KEEP_EXACT):
        if (ROOT / name).exists():
            print(f"  {name}")

    print("\nFolders kept:")
    for name in sorted(KEEP_DIRS):
        if (ROOT / name).exists():
            print(f"  {name}")

if __name__ == "__main__":
    main()
