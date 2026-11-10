"""Remove PARSE_ERROR records from blind-coding results so the runner codes those positions again.

The runner run_blind_coding_through_local_ollama_models.py skips every position
already in results/<slug>/positions.jsonl, including those recorded as
PARSE_ERROR. Deleting these records is the documented way to have them re-coded.

Reads
    <results folder>/<slug>/positions.jsonl for each slug given.

Writes
    <results folder>/previous-versions/<slug>-positions-before-parse-error-recoding-<label>.jsonl
        an untouched copy, made first; the script stops if this copy already exists;
    <results folder>/<slug>/positions.jsonl
        the same records in the same order, without the PARSE_ERROR ones.

Run
    python -I scripts/remove_parse_error_records_for_recoding.py <results folder> <label> <slug> [<slug> ...]
    e.g. python -I scripts/remove_parse_error_records_for_recoding.py results 7-Nov-2026 jais acegpt
"""

import json
import os
import shutil
import sys

PARSE_ERROR_TYPE = "PARSE_ERROR"
POSITIONS_FILE_NAME = "positions.jsonl"
BACKUP_FOLDER_NAME = "previous-versions"
BACKUP_FILE_PATTERN = "{slug}-positions-before-parse-error-recoding-{label}.jsonl"
USAGE = "usage: python -I scripts/remove_parse_error_records_for_recoding.py <results folder> <label> <slug> [<slug> ...]"
MINIMUM_ARGUMENT_COUNT = 4  # the script name, the results folder, the label and at least one slug


def remove_parse_errors(results_folder, label, slug):
    """Back up one model's positions file, then rewrite it without its PARSE_ERROR records.

    Takes the results folder, the label for the backup's file name and the
    model slug. Returns (records kept, records removed). A corrupt line raises
    an error before anything is rewritten, so no record is lost silently."""
    positions_file = os.path.join(results_folder, slug, POSITIONS_FILE_NAME)
    backup_folder = os.path.join(results_folder, BACKUP_FOLDER_NAME)
    os.makedirs(backup_folder, exist_ok=True)
    backup_file = os.path.join(backup_folder, BACKUP_FILE_PATTERN.format(slug=slug, label=label))
    if os.path.exists(backup_file):
        raise SystemExit(f"backup already exists, nothing changed: {backup_file}")
    with open(positions_file, encoding="utf8") as handle:
        lines = [line for line in handle if line.strip()]
    kept = [line for line in lines if json.loads(line).get("type") != PARSE_ERROR_TYPE]
    shutil.copy2(positions_file, backup_file)
    with open(positions_file, "w", encoding="utf8") as handle:
        handle.writelines(kept)
    return len(kept), len(lines) - len(kept)


def main():
    """Apply remove_parse_errors to every slug named on the command line."""
    if len(sys.argv) < MINIMUM_ARGUMENT_COUNT:
        raise SystemExit(USAGE)
    results_folder, label, *slugs = sys.argv[1:]
    for slug in slugs:
        kept, removed = remove_parse_errors(results_folder, label, slug)
        print(f"{slug}: {kept} kept, {removed} removed")


if __name__ == "__main__":
    main()
