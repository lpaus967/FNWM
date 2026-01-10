"""
Update Code References to Use New Schema Names

This script automatically updates all Python code in src/ to reference
the new schema structure (nwm, spatial, observations, derived, validation).

Usage:
    python scripts/db/update_code_schema_references.py              # Dry run (preview)
    python scripts/db/update_code_schema_references.py --apply      # Apply changes
    python scripts/db/update_code_schema_references.py --file path  # Update specific file
"""

import os
import re
import sys
from pathlib import Path
import argparse
from typing import List, Tuple


# Schema mapping: old_table_name → (new_schema, new_table_name)
SCHEMA_MAPPING = {
    # NWM schema
    'hydro_timeseries': ('nwm', 'hydro_timeseries'),
    'ingestion_log': ('nwm', 'ingestion_log'),

    # NHD schema
    'nhd_flowlines': ('nhd', 'flowlines'),
    'nhd_network_topology': ('nhd', 'network_topology'),
    'nhd_flow_statistics': ('nhd', 'flow_statistics'),
    'nhd_reach_centroids': ('nhd', 'reach_centroids'),
    'reach_metadata': ('nhd', 'reach_metadata'),

    # Observations schema
    'USGS_Flowsites': ('observations', 'usgs_flowsites'),
    '"USGS_Flowsites"': ('observations', 'usgs_flowsites'),
    'usgs_instantaneous_values': ('observations', 'usgs_instantaneous_values'),
    'usgs_latest_readings': ('observations', 'usgs_latest_readings'),
    'user_observations': ('observations', 'user_observations'),

    # Derived schema
    'temperature_timeseries': ('observations', 'temperature_timeseries'),
    'computed_scores': ('derived', 'computed_scores'),
    'map_current_conditions': ('derived', 'map_current_conditions'),

    # Validation schema
    'nwm_usgs_validation': ('validation', 'nwm_usgs_validation'),
    'latest_validation_results': ('validation', 'latest_validation_results'),
    'validation_summary': ('validation', 'summary'),
}


def update_sql_queries(content: str) -> Tuple[str, List[str]]:
    """Update SQL queries to include schema names"""
    changes = []
    updated_content = content

    # Pattern 1: FROM table_name or JOIN table_name
    for old_name, (schema, new_name) in SCHEMA_MAPPING.items():
        # Match FROM, JOIN, INTO, UPDATE, DELETE FROM with table name
        patterns = [
            (rf'\b(FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+{re.escape(old_name)}\b',
             rf'\1 {schema}.{new_name}'),
            # Match INSERT INTO
            (rf'\b(INSERT\s+INTO)\s+{re.escape(old_name)}\b',
             rf'\1 {schema}.{new_name}'),
        ]

        for pattern, replacement in patterns:
            if re.search(pattern, updated_content, re.IGNORECASE):
                old_content = updated_content
                updated_content = re.sub(pattern, replacement, updated_content, flags=re.IGNORECASE)
                if old_content != updated_content:
                    changes.append(f"  {old_name} -> {schema}.{new_name}")

    # Pattern 2: Table references in REFERENCES clauses (foreign keys)
    for old_name, (schema, new_name) in SCHEMA_MAPPING.items():
        pattern = rf'\b(REFERENCES)\s+{re.escape(old_name)}\('
        replacement = rf'\1 {schema}.{new_name}('
        if re.search(pattern, updated_content, re.IGNORECASE):
            old_content = updated_content
            updated_content = re.sub(pattern, replacement, updated_content, flags=re.IGNORECASE)
            if old_content != updated_content:
                changes.append(f"  REFERENCES {old_name} -> {schema}.{new_name}")

    # Pattern 3: Direct schema renames (nhd.* -> nhd.*)
    pattern = r'\bspatial\.'
    if re.search(pattern, updated_content, re.IGNORECASE):
        old_content = updated_content
        updated_content = re.sub(pattern, 'nhd.', updated_content, flags=re.IGNORECASE)
        if old_content != updated_content:
            changes.append("  nhd.* -> nhd.*")

    return updated_content, changes


def process_file(file_path: Path, apply: bool = False) -> bool:
    """Process a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        updated_content, changes = update_sql_queries(original_content)

        if changes:
            try:
                rel_path = file_path.relative_to(Path.cwd())
            except ValueError:
                rel_path = file_path
            print(f"\nFile: {rel_path}")
            for change in changes:
                print(change)

            if apply:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                print("  SUCCESS: Updated")
                return True
            else:
                print("  PREVIEW: Would update (use --apply to save changes)")
                return True

        return False

    except Exception as e:
        print(f"ERROR processing {file_path}: {e}")
        return False


def find_python_files(directory: Path) -> List[Path]:
    """Find all Python files in directory"""
    return list(directory.rglob('*.py'))


def main():
    parser = argparse.ArgumentParser(
        description='Update code to use new schema names',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes
  python scripts/db/update_code_schema_references.py

  # Apply changes to all files
  python scripts/db/update_code_schema_references.py --apply

  # Update specific file
  python scripts/db/update_code_schema_references.py --file src/api/main.py --apply
        """
    )
    parser.add_argument('--apply', action='store_true',
                       help='Apply changes to files (default: dry run)')
    parser.add_argument('--file', type=str,
                       help='Update specific file instead of entire src/ directory')
    parser.add_argument('--include-scripts', action='store_true',
                       help='Also update scripts/ directory')
    args = parser.parse_args()

    print("=" * 60)
    print("FNWM Schema Reference Updater")
    print("=" * 60)

    if args.apply:
        print("APPLY MODE: Changes will be written to files")
    else:
        print("DRY RUN MODE: Previewing changes only")
    print()

    # Determine which files to process
    if args.file:
        files_to_process = [Path(args.file)]
        if not files_to_process[0].exists():
            print(f"❌ File not found: {args.file}")
            return 1
    else:
        print("Scanning for Python files...")
        src_dir = Path('src').resolve()
        files_to_process = find_python_files(src_dir)

        if args.include_scripts:
            scripts_dir = Path('scripts')
            files_to_process.extend(find_python_files(scripts_dir))

        print(f"Found {len(files_to_process)} Python files to check")

    # Process files
    files_modified = 0

    for file_path in files_to_process:
        if process_file(file_path, apply=args.apply):
            files_modified += 1

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Files scanned: {len(files_to_process)}")
    print(f"Files with changes: {files_modified}")

    if not args.apply and files_modified > 0:
        print("\nTo apply these changes, run:")
        print("   python scripts/db/update_code_schema_references.py --apply")
    elif args.apply and files_modified > 0:
        print("\nSUCCESS: All changes applied successfully!")
    else:
        print("\nNo changes needed - code is up to date!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
