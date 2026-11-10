"""Build Tables 1 and 2 of the SNM05 paper from the coding files.

    Table 3 is built by three_coders_agreement_fleiss_kappa.py (JQS second-coding scripts folder)
    and Table 4 by verify_blind_coders_quotations_against_windows.py (this folder).

Purpose
    Computes, for every blind coder, its agreement with the Claude coder (the reference coding)
    and writes both tables as Markdown:
    Table A -> paper Table 1: the 624 JQS positions of the first twelve commentaries;
    Table B -> paper Table 2: the 134 Oman positions of al-Hawwari and Himyan al-zad.
    Measures per coder: agreement on the type of position (five types), on vote / no vote, and
    on the chosen view where both coders vote, each as Cohen's kappa with the raw agreement in
    per cent; plus the number of parse errors and the mean seconds per position where the
    coder's files record them (paper Section 4.3, Measures).
    The tables carry the paper's schema (v15): columns Model | Type | Vote | Both vote |
    Same view | Parse errors | Sec./pos., the model names and row order of the paper, kappa
    cells as "0.82 (90)", and the number of positions in the caption line, not in a column.
    The first row of Table A, the Claude blind re-run, is not recomputed (see
    CLAUDE_RERUN_TABLE_A_ROW).

Reads
    JQS_PANEL_MAJORITY_PATH          the reconciled Claude coding of the 624 JQS positions
                                     (reference for Table A), in reference-coding/twelve-commentaries/stage1-output.
    JQS_RESULTS_FOLDER/results/<coder>/*.jsonl
                                     every other coder's JQS coding, one JSON object per line,
                                     in first-twelve-commentaries/second-coding-by-external-AI.
    blind-coding/results/claude/*.jsonl
                                     the Claude coding of the 134 Oman positions (reference for Table B).
    blind-coding/results/<coder>/*.jsonl
                                     every other coder's Oman coding.
    Each line holds at least "row", "who", "type" and "holds"; the Ollama runner adds "seconds".
    A line that is not valid JSON is skipped and counted, and the count is printed per folder;
    a row that is not an integer stops the run with a message naming the file.
    The three project folders are siblings under the Claude working folder (the parent of
    this paper folder), so the script runs wherever that folder is checked out.

Writes
    blind-coding/results/All-coders-results-tables.md (or the same name under --out-dir; with
    --date the file is All-coders-results-tables-<YYYY-MM-DD>.md instead, for a dated snapshot:
    the date given, or today's when --date stands alone) and prints the same Markdown. The
    static name keeps the references to this file in the results notes and the paper valid
    from run to run.

Run
    python -I scripts/build_all_coders_results_tables.py [--out-dir FOLDER] [--date [YYYY-MM-DD]]

How the measures are built
    Positions are matched on (row, who). Every position of the reference is compared: a position
    the coder did not return at all is given the type MISSING and the vote category MISSING on
    the coder's side, so it counts as a disagreement on type and on vote, and the number of such
    positions is printed under each table (no coder is missing a position to date).
    Type: the coder's type as written (the five types of the rule, plus PARSE_ERROR where the
    runner could not read the model's answer, plus MISSING), against the reference type.
    Vote: "vote" for prefers and single, "no vote" for combines, lists_no_choice and silent, and
    ERROR for a PARSE_ERROR, so that a parse error never agrees with the reference, whichever way
    the reference goes (a parse error is not an answer, so it is not a "no vote" either).
    Same view: over the positions where both coders vote, the SET of view ids in "holds" of each
    coder, compared for equality. The rule allows exactly one view for prefers and single, so the
    reference always holds one id; a coder that lists several ids on a vote (ALLaM 7B does on 228
    of the 624 positions, Falcon-H1 7B on 23, Jais 13B on 22, Gemini 3 Pro, Gemma 3 12B,
    DeepSeek-R1 14B and Fanar 9B on one each) has departed from the rule and therefore disagrees
    unless the reference lists the same set. Each coder's value is the sorted ids joined by "+"
    (one nominal label per position, pooled across points, as the paper states), so that Cohen's
    kappa applies unchanged.

How kappa is computed
    Cohen's kappa = (p_o - p_e) / (1 - p_e), where p_o is the observed proportion of positions
    on which the two coders agree and p_e the agreement expected by chance, the sum over all
    categories of (share of category in coder 1) x (share of category in coder 2). With one
    category only (p_e = 1) the formula has no denominator and kappa is undefined: it is returned
    as nan and printed as an empty cell (the paper's Table 2, Jais 13B, same view); with no
    positions it is nan as well.
"""

import argparse
import datetime
import glob
import json
import os

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_WORKING_FOLDER = os.path.dirname(PROJECT_FOLDER)  # the folder that holds all the paper projects
OMAN_RESULTS_FOLDER = os.path.join(PROJECT_FOLDER, "blind-coding", "results")
JQS_RESULTS_FOLDER = os.path.join(CLAUDE_WORKING_FOLDER, "first-twelve-commentaries", "second-coding-by-external-AI")
JQS_PANEL_MAJORITY_PATH = os.path.join(CLAUDE_WORKING_FOLDER, "reference-coding", "twelve-commentaries",
                                       "stage1-output", "panel-majority.json")
OUTPUT_FILE_NAME = "All-coders-results-tables.md"
DATED_OUTPUT_FILE_NAME_PATTERN = "All-coders-results-tables-{date}.md"
DATE_ARGUMENT_FORMAT = "%Y-%m-%d"  # the form of the --date value

REFERENCE_CODER_FOLDER = "claude"
VOTING_TYPES = {"prefers", "single"}  # the two position types that count as a vote for a view
PARSE_ERROR_TYPE = "PARSE_ERROR"  # type written by the runners when a model's output did not satisfy the schema
MISSING_LABEL = "MISSING"  # type and vote category of a reference position the coder did not return
VOTE_LABEL = "vote"
NO_VOTE_LABEL = "no vote"
VOTE_ERROR_LABEL = "ERROR"  # vote category of a parse error: equal to neither "vote" nor "no vote"
VIEW_ID_SEPARATOR = "+"  # joins the sorted view ids of one vote into one nominal label, e.g. "a+b"

# coder slug (results folder name) -> model name as printed in the paper's Tables 1 and 2 (v15)
CODER_NAMES = {
    "claude-rerun": "Claude Opus 5.5, blind re-run",
    "gemini": "Gemini 3 Pro",
    "qwen": "Qwen3 14B",
    "gemma": "Gemma 3 12B",
    "deepseek": "DeepSeek-R1 14B",
    "fanar": "Fanar 9B",
    "llama": "Llama 3.1 8B",
    "falcon": "Falcon-H1 7B",
    "acegpt": "AceGPT-v2 8B",
    "allam": "ALLaM 7B",
    "jais": "Jais 13B",
}
CODER_ORDER = ["claude-rerun", "gemini", "qwen", "gemma", "deepseek", "fanar", "llama", "falcon", "acegpt", "allam", "jais"]  # the paper's row order
CLAUDE_RERUN_SLUG = "claude-rerun"

# The Claude blind re-run of 23 Oct 2026 was compared with the first coding BEFORE the 52 disagreements
# were resolved (JQS article, Method). The reference used for every other row is the reconciled coding,
# which incorporates the re-run, so the re-run's figures cannot be recomputed here against that reference:
# the row carries the published figures of the first Table 1 row of the paper, taken from the line
# "All twelve | 609" of (relative to the Claude working folder, CLAUDE_WORKING_FOLDER)
# reference-coding/twelve-commentaries/stage1-output/independent-coding/second-coder-comparison.md
# (609 positions; type kappa 0.89, 93 %; vote kappa 0.91, 96 %; both vote 181; same view kappa 0.98, 99 %;
# no parse error; no timing recorded). The re-run is absent from Table B.
CLAUDE_RERUN_TABLE_A_ROW = "| Claude Opus 5.5, blind re-run | 0.89 (93) | 0.91 (96) | 181 | 0.98 (99) | 0 | |"

# The paper's table schema: the positions count stands in the caption line, not in a column.
TABLE_HEADER = ("| Model | Type | Vote | Both vote | Same view | Parse errors | Sec./pos. |\n"
                "|---|---|---|---|---|---|---|")
TABLE_COLUMN_COUNT = 7  # columns of TABLE_HEADER; the fallback row for an empty coder must have as many cells
TABLE_A_TITLE = ("## Table A (paper Table 1). Agreement with the Claude coder on the 624 positions of the first twelve "
                 "commentaries (N = 624; 609 for the Claude re-run)")
TABLE_B_TITLE = "## Table B (paper Table 2). Agreement with the Claude coder on the 134 positions of al-Hawwari and Himyan al-zad (N = 134)"
MISSING_NOTE_PREFIX = "Positions of the reference absent from a coder's output (counted as disagreements on type and vote): "


def cohens_kappa(pairs):
    """Return Cohen's kappa for a list of (coder 1 label, coder 2 label) pairs.

    nan when the list is empty, and nan when the expected agreement is 1 (both coders used one
    category only), because the formula then has no denominator and kappa is undefined.
    """
    count = len(pairs)
    if count == 0:
        return float("nan")
    observed_agreement = sum(label_1 == label_2 for label_1, label_2 in pairs) / count
    categories = set(label_1 for label_1, _ in pairs) | set(label_2 for _, label_2 in pairs)
    expected_agreement = sum(
        (sum(label_1 == category for label_1, _ in pairs) / count) * (sum(label_2 == category for _, label_2 in pairs) / count)
        for category in categories)
    if expected_agreement >= 1:
        return float("nan")
    return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def view_label(record):
    """Return the sorted view ids in "holds" joined by "+", one nominal label for the same-view comparison.

    A vote holds one id under the rule, so the reference label is that id; a coder that lists
    several ids gets a label such as "a+b", which equals the reference label only when the
    reference lists the same set. Empty "holds" gives "".
    """
    return VIEW_ID_SEPARATOR.join(sorted(str(view_id) for view_id in record.get("holds") or []))


def position_key(row, who, source):
    """Return the key (int(row), who) of one record; stop with a clear message when the row is not an integer."""
    if isinstance(row, bool) or not isinstance(row, (int, str)) or (isinstance(row, str) and not row.strip().isdigit()):
        raise ValueError(f"{source}: row {row!r} is not an integer")
    return int(row), who


def load_jsonl_folder(folder):
    """Return {(int(row), who): record} from every *.jsonl file in the folder, files in name order, later lines winning.

    A line that is not valid JSON is skipped; the number of such lines is printed when there are any.
    """
    records = {}
    unreadable_lines = 0
    for path in sorted(glob.glob(os.path.join(folder, "*.jsonl"))):
        with open(path, encoding="utf8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    unreadable_lines += 1
                    continue
                records[position_key(record.get("row"), record.get("who"), f"{path} line {line_number}")] = record
    if unreadable_lines:
        print(f"{folder}: {unreadable_lines} line(s) not valid JSON, skipped")
    return records


def vote_label(position_type):
    """Return the vote category of a position type: "vote", "no vote", ERROR for a parse error, MISSING passed through."""
    if position_type == PARSE_ERROR_TYPE:
        return VOTE_ERROR_LABEL
    if position_type == MISSING_LABEL:
        return MISSING_LABEL
    return VOTE_LABEL if position_type in VOTING_TYPES else NO_VOTE_LABEL


def coder_type(other, key):
    """Return the coder's type for a reference position, or MISSING when the coder did not return it."""
    return other[key]["type"] if key in other else MISSING_LABEL


def format_kappa_cell(pairs):
    """Return 'kappa (percent agree)' for a list of label pairs, or an empty cell when there are none or kappa is undefined."""
    if not pairs:
        return ""
    kappa = cohens_kappa(pairs)
    if kappa != kappa:  # nan: undefined kappa; the paper leaves the whole cell empty (Table 2, Jais 13B, same view)
        return ""
    percent_agree = 100 * sum(label_1 == label_2 for label_1, label_2 in pairs) / len(pairs)
    return f"{kappa:.2f} ({percent_agree:.0f})"


def table_row(coder_name, reference, other):
    """Return (Markdown table row, number of missing positions) comparing a coder with the reference.

    Every reference position is compared, matched on (row, who); a position absent from the coder's
    output is typed MISSING on the coder's side. The same-view comparison uses the set of ids in
    "holds" of each coder (view_label), over the positions where both record a vote (see the
    module docstring).
    """
    reference_keys = list(reference)
    if not any(key in other for key in reference_keys):
        # One empty cell per header column after the name, so the Markdown table stays well formed.
        empty_cells = " | ".join([""] * (TABLE_COLUMN_COUNT - 1))
        return f"| {coder_name} | {empty_cells} |", len(reference_keys)
    type_pairs = [(reference[key]["type"], coder_type(other, key)) for key in reference_keys]
    vote_pairs = [(vote_label(reference_type), vote_label(other_type)) for reference_type, other_type in type_pairs]
    both_vote_keys = [key for key in reference_keys
                      if reference[key]["type"] in VOTING_TYPES and coder_type(other, key) in VOTING_TYPES]
    view_pairs = [(view_label(reference[key]), view_label(other[key])) for key in both_vote_keys]
    parse_errors = sum(other_type == PARSE_ERROR_TYPE for _, other_type in type_pairs)
    missing = sum(other_type == MISSING_LABEL for _, other_type in type_pairs)
    seconds = [other[key]["seconds"] for key in reference_keys if key in other and "seconds" in other[key]]
    mean_seconds = f"{sum(seconds) / len(seconds):.0f}" if seconds else ""
    row = (f"| {coder_name} | {format_kappa_cell(type_pairs)} | {format_kappa_cell(vote_pairs)} | "
           f"{len(both_vote_keys)} | {format_kappa_cell(view_pairs)} | {parse_errors} | {mean_seconds} |")
    return row, missing


def missing_note(missing_by_coder):
    """Return the line printed under a table that reports the missing positions per coder, or 'none'."""
    missing_coders = [f"{coder_name} {missing}" for coder_name, missing in missing_by_coder.items() if missing]
    return MISSING_NOTE_PREFIX + ("; ".join(missing_coders) if missing_coders else "none") + "."


def load_jqs_reference():
    """Return the reconciled Claude coding of the 624 JQS positions as {(row, who): {"type", "holds"}}."""
    reference = {}
    with open(JQS_PANEL_MAJORITY_PATH, encoding="utf8") as handle:
        points = json.load(handle)
    for point in points:
        for who, position in point["positions"].items():
            reference[position_key(point["n"], who, JQS_PANEL_MAJORITY_PATH)] = {
                "type": position["type"], "holds": position.get("holds", [])}
    return reference


def build_tables():
    """Return the Markdown text of Table A (JQS, 624 positions) and Table B (Oman, 134 positions)."""
    lines = []
    jqs_reference = load_jqs_reference()
    lines.append(f"{TABLE_A_TITLE}\n\n{TABLE_HEADER}")
    missing_by_coder = {}
    for slug in CODER_ORDER:
        if slug == CLAUDE_RERUN_SLUG:
            lines.append(CLAUDE_RERUN_TABLE_A_ROW)
            continue
        row, missing_by_coder[CODER_NAMES[slug]] = table_row(
            CODER_NAMES[slug], jqs_reference, load_jsonl_folder(os.path.join(JQS_RESULTS_FOLDER, "results", slug)))
        lines.append(row)
    lines.append("\n" + missing_note(missing_by_coder))
    oman_reference = load_jsonl_folder(os.path.join(OMAN_RESULTS_FOLDER, REFERENCE_CODER_FOLDER))
    lines.append(f"\n{TABLE_B_TITLE}\n\n{TABLE_HEADER}")
    missing_by_coder = {}
    for slug in CODER_ORDER:
        if slug == CLAUDE_RERUN_SLUG:
            continue
        row, missing_by_coder[CODER_NAMES[slug]] = table_row(
            CODER_NAMES[slug], oman_reference, load_jsonl_folder(os.path.join(OMAN_RESULTS_FOLDER, slug)))
        lines.append(row)
    lines.append("\n" + missing_note(missing_by_coder))
    return "\n".join(lines)


def parse_date(text):
    """Return the date written as YYYY-MM-DD, for the --date argument."""
    return datetime.datetime.strptime(text, DATE_ARGUMENT_FORMAT).date()


def main():
    """Build both tables, print them and write them to the results folder (or --out-dir), dated only with --date."""
    parser = argparse.ArgumentParser(description="Build the SNM05 results tables (Tables 1 and 2) as Markdown.")
    parser.add_argument("--out-dir", default=OMAN_RESULTS_FOLDER,
                        help=f"folder for the Markdown file (default: {OMAN_RESULTS_FOLDER})")
    parser.add_argument("--date", nargs="?", const=datetime.date.today(), default=None, type=parse_date,
                        metavar="YYYY-MM-DD",
                        help=f"write {DATED_OUTPUT_FILE_NAME_PATTERN.format(date='YYYY-MM-DD')} (today's date when no "
                             f"value is given) instead of {OUTPUT_FILE_NAME}")
    arguments = parser.parse_args()
    text = build_tables()
    file_name = DATED_OUTPUT_FILE_NAME_PATTERN.format(date=arguments.date) if arguments.date else OUTPUT_FILE_NAME
    output_path = os.path.join(arguments.out_dir, file_name)
    with open(output_path, "w", encoding="utf8") as handle:
        handle.write(text + "\n")
    print(text)
    print("\nwritten", output_path)


if __name__ == "__main__":
    main()
