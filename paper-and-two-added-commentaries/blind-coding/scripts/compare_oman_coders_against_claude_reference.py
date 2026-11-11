"""Compare every blind coder's coding of the 134 Oman positions with the Claude reference coding.

Purpose
    For each coder folder under blind-coding/results (Gemini 3 Pro and the nine Ollama models)
    computes the agreement with the Claude coder on the 134 positions of packets 26 and 27
    (al-Hawwari and Himyan al-zad, 67 each): agreement on the type of position (five types),
    on vote / no vote, and on the chosen view where both coders vote, each with Cohen's kappa.
    These are the figures summarised in paper Section 5.2 and Table 2 (the Markdown table
    itself is built by scripts/build_all_coders_results_tables.py in the paper folder).

Reads
    results/claude/*.jsonl    the reference coding (Claude coder), one JSON object per line
                              with "row", "who", "type", "holds", "quote", "note".
    results/<coder>/*.jsonl   every other coder's coding in the same line format
                              (positions.jsonl from the Ollama runner, blind-packet-*.jsonl
                              from the Gemini CLI runner). The folders in SKIPPED_FOLDERS
                              are not coders and are ignored. A line that is not valid JSON
                              is skipped and counted, and the count is printed per folder; a
                              row that is not an integer stops the run with a message naming
                              the file.

Writes
    results/<coder>/merged-positions.json   the coder's records for the positions both coded,
                                            in reference order
    results/<coder>/disagreements.tsv       one line per position where type or (for votes)
                                            the views held differ, with the coder's quote;
                                            a position the coder did not return is listed
                                            with the type MISSING
    (or the same files under <out-dir>/<coder>/ with --out-dir) and prints one tab-separated
    row per coder: reference positions compared, positions missing from the coder's output,
    type agreement and kappa, vote agreement and kappa, positions where both vote, same view
    and kappa.

Run (from the blind-coding folder)
    python -I scripts/compare_oman_coders_against_claude_reference.py [--out-dir FOLDER]

How the measures are built
    Positions are matched on (row, who). Every position of the reference is compared: a position
    the coder did not return at all is given the type MISSING and the vote category MISSING on
    the coder's side, so it counts as a disagreement on type and on vote; the number of such
    positions is printed per coder (no coder is missing a position to date).
    Type: the coder's type as written (the five types of the rule, plus PARSE_ERROR where the
    runner could not read the model's answer, plus MISSING), against the reference type.
    Vote: "vote" for prefers and single, "no vote" for combines, lists_no_choice and silent, and
    ERROR for a PARSE_ERROR, so that a parse error never agrees with the reference, whichever way
    the reference goes (a parse error is not an answer, so it is not a "no vote" either).
    Same view: over the positions where both coders vote, the SET of view ids in "holds" of each
    coder, compared for equality. The rule allows exactly one view for prefers and single, so the
    reference always holds one id; a coder that lists several ids on a vote (ALLaM 7B does on 48
    of the 134 positions, Falcon-H1 7B on 8) has departed from the rule and therefore disagrees
    unless the reference lists the same set. Each coder's value is the sorted ids joined by "+"
    (one nominal label per position, pooled across points, as the paper states), so that Cohen's
    kappa applies unchanged. disagreements.tsv lists the held views by the same comparison.

How kappa is computed
    Cohen's kappa = (p_o - p_e) / (1 - p_e): p_o is the observed share of agreeing positions,
    p_e the agreement expected by chance, the sum over categories of (share in coder 1) x
    (share in coder 2). With one category only (p_e = 1) the formula has no denominator and
    kappa is undefined: it is nan and printed as an empty cell (no case in the paper); with no
    positions it is nan as well (the paper's Table 2, Jais 13B, same view: no position on which
    both vote).
"""

import argparse
import csv
import glob
import json
import os

BLIND_CODING_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_FOLDER = os.path.join(BLIND_CODING_FOLDER, "results")
REFERENCE_CODER_FOLDER = "claude"
SKIPPED_FOLDERS = ("claude", "previous-versions", "logs")  # not coder folders
VOTING_TYPES = {"prefers", "single"}  # the two position types that count as a vote for a view
PARSE_ERROR_TYPE = "PARSE_ERROR"  # type written by the runners when a model's output did not satisfy the schema
MISSING_LABEL = "MISSING"  # type and vote category of a reference position the coder did not return
VOTE_LABEL = "vote"
NO_VOTE_LABEL = "no vote"
VOTE_ERROR_LABEL = "ERROR"  # vote category of a parse error: equal to neither "vote" nor "no vote"
VIEW_ID_SEPARATOR = "+"  # joins the sorted view ids of one vote into one nominal label, e.g. "a+b"
UNDEFINED_KAPPA_TEXT = ""  # an empty cell where kappa has no denominator (one category only), as in the paper's Table 2 Jais row
QUOTE_COLUMN_MAX_CHARACTERS = 120  # the coder's quote is cut in disagreements.tsv to keep the file readable
MERGED_FILE_NAME = "merged-positions.json"
DISAGREEMENTS_FILE_NAME = "disagreements.tsv"


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


def cohens_kappa(pairs):
    """Return Cohen's kappa for a list of (coder 1 label, coder 2 label) pairs.

    nan when the list is empty, and nan when the expected agreement is 1 (both coders used one
    category only), because the formula then has no denominator and kappa is undefined.
    """
    count = len(pairs)
    if not count:
        return float("nan")
    observed_agreement = sum(label_1 == label_2 for label_1, label_2 in pairs) / count
    categories = set(label_1 for label_1, _ in pairs) | set(label_2 for _, label_2 in pairs)
    expected_agreement = sum(
        (sum(label_1 == category for label_1, _ in pairs) / count) * (sum(label_2 == category for _, label_2 in pairs) / count)
        for category in categories)
    if expected_agreement >= 1:
        return float("nan")
    return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def format_kappa(kappa):
    """Return kappa with two decimals, or an empty cell when it is nan (undefined)."""
    return UNDEFINED_KAPPA_TEXT if kappa != kappa else f"{kappa:.2f}"


def view_label(record):
    """Return the sorted view ids in "holds" joined by "+", one nominal label for the same-view comparison.

    A vote holds one id under the rule, so the reference label is that id; a coder that lists
    several ids gets a label such as "a+b", which equals the reference label only when the
    reference lists the same set. Empty "holds" gives "".
    """
    return VIEW_ID_SEPARATOR.join(sorted(str(view_id) for view_id in record.get("holds") or []))


def held_views_text(record):
    """Return the view ids in "holds" joined by spaces, as written in disagreements.tsv."""
    return " ".join(str(view_id) for view_id in record.get("holds") or [])


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


def list_coder_folders(results_folder):
    """Return the coder folder names under results, in alphabetical order, without the reference and helper folders."""
    return sorted(name for name in os.listdir(results_folder)
                  if name not in SKIPPED_FOLDERS and os.path.isdir(os.path.join(results_folder, name)))


def write_disagreements(path, coder, reference, other):
    """Write the TSV of reference positions where the coder's type differs (MISSING when absent), or both vote and the views differ."""
    with open(path, "w", encoding="utf8", newline="") as tsv_file:
        writer = csv.writer(tsv_file, delimiter="\t")
        writer.writerow(["row", "who", "claude type", "claude holds", f"{coder} type", f"{coder} holds", f"{coder} quote"])
        for key, reference_record in reference.items():
            other_record = other.get(key, {"type": MISSING_LABEL, "holds": [], "quote": ""})
            if reference_record["type"] != other_record["type"] or (
                    reference_record["type"] in VOTING_TYPES and view_label(reference_record) != view_label(other_record)):
                writer.writerow([key[0], key[1], reference_record["type"], held_views_text(reference_record),
                                 other_record["type"], held_views_text(other_record),
                                 (other_record.get("quote") or "")[:QUOTE_COLUMN_MAX_CHARACTERS]])


def compare_coder(coder, reference, other, output_folder):
    """Write the coder's merged positions and disagreements and return its tab-separated result row.

    Every reference position is compared, matched on (row, who), in reference order; a position
    absent from the coder's output is typed MISSING on the coder's side. The same-view comparison
    uses the set of ids in "holds" of each coder (view_label), over the positions where both
    record a vote (see the module docstring). Returns None when the coder shares no position with
    the reference.
    """
    reference_keys = list(reference)
    if not any(key in other for key in reference_keys):
        return None
    coder_output_folder = os.path.join(output_folder, coder)
    os.makedirs(coder_output_folder, exist_ok=True)
    with open(os.path.join(coder_output_folder, MERGED_FILE_NAME), "w", encoding="utf8") as handle:
        json.dump([other[key] for key in reference_keys if key in other], handle, ensure_ascii=False, indent=1)
    type_pairs = [(reference[key]["type"], coder_type(other, key)) for key in reference_keys]
    vote_pairs = [(vote_label(reference_type), vote_label(other_type)) for reference_type, other_type in type_pairs]
    both_vote_keys = [key for key in reference_keys
                      if reference[key]["type"] in VOTING_TYPES and coder_type(other, key) in VOTING_TYPES]
    view_pairs = [(view_label(reference[key]), view_label(other[key])) for key in both_vote_keys]
    write_disagreements(os.path.join(coder_output_folder, DISAGREEMENTS_FILE_NAME), coder, reference, other)
    missing = sum(other_type == MISSING_LABEL for _, other_type in type_pairs)
    type_agree = sum(label_1 == label_2 for label_1, label_2 in type_pairs)
    vote_agree = sum(label_1 == label_2 for label_1, label_2 in vote_pairs)
    view_agree = sum(label_1 == label_2 for label_1, label_2 in view_pairs)
    return (f"{coder}\t{len(reference_keys)}\t{missing}\t{type_agree} ({100 * type_agree / len(type_pairs):.0f}%)\t"
            f"{format_kappa(cohens_kappa(type_pairs))}\t{vote_agree} ({100 * vote_agree / len(vote_pairs):.0f}%)\t"
            f"{format_kappa(cohens_kappa(vote_pairs))}\t{len(both_vote_keys)}\t{view_agree}\t"
            f"{format_kappa(cohens_kappa(view_pairs))}")


def main():
    """Load the reference coding, compare every coder folder with it and print one row per coder."""
    parser = argparse.ArgumentParser(description="Compare every coder's Oman coding with the Claude reference coding.")
    parser.add_argument("--out-dir", default=RESULTS_FOLDER,
                        help=f"folder under which <coder>/merged-positions.json and disagreements.tsv are written (default: {RESULTS_FOLDER})")
    arguments = parser.parse_args()
    reference = load_jsonl_folder(os.path.join(RESULTS_FOLDER, REFERENCE_CODER_FOLDER))
    print(f"reference (Claude coder): {len(reference)} positions")
    print("coder\tcompared\tmissing\ttype agree\tkappa\tvote agree\tkappa\tboth vote\tsame view\tkappa")
    for coder in list_coder_folders(RESULTS_FOLDER):
        result_row = compare_coder(coder, reference, load_jsonl_folder(os.path.join(RESULTS_FOLDER, coder)), arguments.out_dir)
        if result_row:
            print(result_row)


if __name__ == "__main__":
    main()
