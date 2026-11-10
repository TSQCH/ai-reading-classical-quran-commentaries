"""Merge one AI coder's blind-coding answers and compare them with the first coder.

Purpose
    Each external coder answers in JSON Lines: one object per position with
    row, who, type, holds, quote, note (packet coders such as Gemini write one
    file per packet, the local Ollama runner writes positions.jsonl). This
    script merges those lines into one file and measures agreement with the
    first coder on three questions: the type given to the position, whether
    the commentator is read as voting (prefers or single) or not, and, where
    both read him as voting, whether they name the same view. Each is reported
    as a count, a percentage and Cohen's kappa.

Reads
    <results_folder>/*.jsonl
        the coder's answers (blind-packet-NN-of-24.jsonl, blind-packet-25-of-25.jsonl,
        or positions.jsonl). Lines that do not start with "{" (code fences, prose)
        are skipped; a line that starts with "{" but is not valid JSON is skipped
        and counted, and the count is printed. A row that is not an integer stops
        the run with a message naming the file.
    <panel_majority.json>
        the first coder's panel file (stage1-output/panel-majority.json): one
        record per phrase, n = row, positions[<who>] = {type, holds, ...}.

Writes (to --out-dir, default the results folder)
    merged-positions.json   the final answer for each position of the reference coding,
                            in its order, as one JSON array (a position answered twice
                            keeps its later answer)
    disagreements.tsv       row, who, first coder's type, second coder's type, first
                            coder's held views, second coder's held views, for every
                            position where the types differ or where both coders vote
                            but not for the same view (the view labels differ); a
                            position the coder did not return is listed with the type
                            MISSING

Prints
    positions in the first coder's file, positions returned by the coder and
    positions missing; type agreement, vote/no-vote agreement, and view
    agreement where both vote, each with Cohen's kappa; then the number of
    disagreements written (type disagreements plus view disagreements).

Run
    python -I merge_external_ai_results_and_compare.py <results_folder> <panel_majority.json> [--out-dir FOLDER]

How the measures are built
    Positions are matched on (row, who). Every position of the first coder is
    compared: a position the second coder did not return at all is given the
    type MISSING and the vote category MISSING on his side, so it counts as a
    disagreement on type and on vote (no coder is missing a position to date).
    Type: the coder's type as written (the five types of the rule, plus
    PARSE_ERROR where the runner could not read the model's answer, plus
    MISSING), against the first coder's type.
    Vote: "vote" for prefers and single, "no vote" for combines, lists_no_choice
    and silent, and ERROR for a PARSE_ERROR, so that a parse error never agrees
    with the first coder, whichever way he goes (a parse error is not an answer,
    so it is not a "no vote" either).
    Same view: over the positions where both coders vote, the SET of view ids
    in "holds" of each coder, compared for equality. The rule allows exactly
    one view for prefers and single, so the first coder always holds one id;
    a coder that lists several ids on a vote (ALLaM 7B does on 228 of the 624
    positions, Falcon-H1 7B on 23, Jais 13B on 22, Gemini 3 Pro, Gemma 3 12B,
    DeepSeek-R1 14B and Fanar 9B on one each) has departed from the rule and
    therefore disagrees unless the first coder lists the same set. Each
    coder's value is the sorted ids joined by "+" (one nominal label per
    position, pooled across points, as the papers state), so that Cohen's
    kappa applies unchanged. disagreements.tsv lists the held views by the
    same comparison.
    Cohen's kappa = (p_o - p_e) / (1 - p_e); with one category only (p_e = 1)
    the formula has no denominator and kappa is undefined: it is nan and
    printed as "n/a"; with no positions it is nan as well.

Feeds
    The per-coder rows of the agreement tables in
    results/Gemini-second-coding-results-and-three-coder-agreement-2026-11-02.md
    and results/Nine-local-models-results-and-agreement-2026-11-04.md, and
    hence the second-coding figures in the JQS article and the SNM05 paper.
"""

import argparse
import glob
import json
import os

# Only these two types are a vote for one view.
VOTING_TYPES = ("prefers", "single")
PARSE_ERROR_TYPE = "PARSE_ERROR"  # type written by the runners when a model's output did not satisfy the schema
MISSING_LABEL = "MISSING"  # type and vote category of a first-coder position the second coder did not return
VOTE_LABEL = "vote"
NO_VOTE_LABEL = "no vote"
VOTE_ERROR_LABEL = "ERROR"  # vote category of a parse error: equal to neither "vote" nor "no vote"
VIEW_ID_SEPARATOR = "+"  # joins the sorted view ids of one vote into one nominal label, e.g. "a+b"
UNDEFINED_KAPPA_TEXT = "n/a"  # printed where kappa has no denominator (one category only)

MERGED_FILE_NAME = "merged-positions.json"
DISAGREEMENTS_FILE_NAME = "disagreements.tsv"
HELD_VIEWS_SEPARATOR = " "  # joins the view ids of one coder in disagreements.tsv


def read_answer_lines(results_folder):
    """Read every JSON object line from the coder's *.jsonl files, in file
    name order. Returns the list of parsed objects.

    A line is stripped of surrounding whitespace and backticks first, because
    chat models sometimes wrap the output in a ``` code fence; anything that
    then does not start with "{" is not an answer and is skipped. A line that
    starts with "{" but is not valid JSON is skipped too, and the number of
    such lines is printed when there are any.
    """
    answers = []
    unreadable_lines = 0
    for path in sorted(glob.glob(os.path.join(results_folder, "*.jsonl"))):
        with open(path, encoding="utf8") as handle:
            for line in handle:
                line = line.strip().strip("`")
                if not line.startswith("{"):
                    continue
                try:
                    answers.append(json.loads(line))
                except json.JSONDecodeError:
                    unreadable_lines += 1
    if unreadable_lines:
        print(f"{results_folder}: {unreadable_lines} line(s) not valid JSON, skipped")
    return answers


def position_key(row, who, source):
    """Return the key (int(row), who) of one record; stop with a clear message when the row is not an integer."""
    if isinstance(row, bool) or not isinstance(row, (int, str)) or (isinstance(row, str) and not row.strip().isdigit()):
        raise ValueError(f"{source}: row {row!r} is not an integer")
    return int(row), who


def first_coder_positions(panel_majority_path):
    """Return {(int(row), who): position record} from panel-majority.json (n = row)."""
    with open(panel_majority_path, encoding="utf8") as handle:
        records = json.load(handle)
    return {position_key(record["n"], who, panel_majority_path): position
            for record in records for who, position in record["positions"].items()}


def second_coder_positions(answers, results_folder):
    """Return {(int(row), who): answer} from the merged answer lines.
    If a coder answered a position twice, the later line wins."""
    return {position_key(answer.get("row"), answer.get("who"), results_folder): answer for answer in answers}


def cohen_kappa(pairs):
    """Cohen's kappa, unweighted, for a list of (first code, second code) pairs.

    Observed agreement p_o is the share of pairs whose two codes are equal.
    Expected agreement p_e is the sum, over every category used by either
    coder, of the product of the two coders' marginal proportions for that
    category. kappa = (p_o - p_e) / (1 - p_e); nan when there are no pairs,
    and nan when p_e is 1 (both coders gave one category only, so the formula
    has no denominator and kappa is undefined).
    """
    pair_count = len(pairs)
    if pair_count == 0:
        return float("nan")
    categories = set(first for first, second in pairs) | set(second for first, second in pairs)
    observed = sum(first == second for first, second in pairs) / pair_count
    expected = sum(
        (sum(first == category for first, second in pairs) / pair_count)
        * (sum(second == category for first, second in pairs) / pair_count)
        for category in categories)
    if expected >= 1:
        return float("nan")
    return (observed - expected) / (1 - expected)


def format_kappa(kappa):
    """kappa with two decimals, or "n/a" when it is nan (undefined)."""
    return UNDEFINED_KAPPA_TEXT if kappa != kappa else f"{kappa:.2f}"


def vote_label(position_type):
    """The vote category of a position type: "vote", "no vote", ERROR for a
    parse error, MISSING passed through unchanged."""
    if position_type == PARSE_ERROR_TYPE:
        return VOTE_ERROR_LABEL
    if position_type == MISSING_LABEL:
        return MISSING_LABEL
    return VOTE_LABEL if position_type in VOTING_TYPES else NO_VOTE_LABEL


def coder_type(second, key):
    """The second coder's type for a first-coder position, or MISSING when
    the second coder did not return it."""
    return second[key]["type"] if key in second else MISSING_LABEL


def view_label(position):
    """The sorted view ids in "holds" joined by "+", one nominal label for the
    same-view comparison. A vote holds one id under the rule, so the first
    coder's label is that id; a coder that lists several ids gets a label such
    as "a+b", which equals the first coder's only when he lists the same set.
    Empty "holds" gives ""."""
    return VIEW_ID_SEPARATOR.join(sorted(str(view_id) for view_id in position.get("holds") or []))


def held_views_text(position):
    """The view ids in "holds" joined by spaces, as written in disagreements.tsv."""
    return HELD_VIEWS_SEPARATOR.join(str(view_id) for view_id in position.get("holds") or [])


def report_agreement(first, second):
    """Print the three agreement measures and return the list of
    (key, first type, second type, first held views, second held views) for
    the positions where the types differ, a missing position counting as the
    type MISSING, or where both coders vote but their view labels differ."""
    compared_keys = list(first)
    type_pairs = [(first[key]["type"], coder_type(second, key)) for key in compared_keys]
    vote_pairs = [(vote_label(first_type), vote_label(second_type)) for first_type, second_type in type_pairs]
    both_vote_keys = [key for key in compared_keys
                      if first[key]["type"] in VOTING_TYPES and coder_type(second, key) in VOTING_TYPES]
    view_pairs = [(view_label(first[key]), view_label(second[key])) for key in both_vote_keys]

    missing = sum(second_type == MISSING_LABEL for _, second_type in type_pairs)
    type_agree = sum(first_type == second_type for first_type, second_type in type_pairs)
    vote_agree = sum(first_vote == second_vote for first_vote, second_vote in vote_pairs)
    print(f"positions compared {len(compared_keys)}: returned by the coder {len(compared_keys) - missing}, "
          f"missing {missing} (counted as disagreements)")
    print(f"type agree {type_agree} ({100 * type_agree / len(type_pairs):.1f}%), kappa {format_kappa(cohen_kappa(type_pairs))}")
    print(f"vote/no vote agree {vote_agree} ({100 * vote_agree / len(vote_pairs):.1f}%), kappa {format_kappa(cohen_kappa(vote_pairs))}")
    if view_pairs:
        same_view = sum(first_label == second_label for first_label, second_label in view_pairs)
        print(f"both vote {len(both_vote_keys)}, same view {same_view}, kappa {format_kappa(cohen_kappa(view_pairs))}")

    missing_position = {"type": MISSING_LABEL, "holds": []}
    return [(key, first_type, second_type, held_views_text(first[key]), held_views_text(second.get(key, missing_position)))
            for key, (first_type, second_type) in zip(compared_keys, type_pairs)
            if first_type != second_type or (key in both_vote_keys and view_label(first[key]) != view_label(second[key]))]


def write_disagreements(disagreements, output_path):
    """Write the type and view disagreements as a TSV with a header line."""
    with open(output_path, "w", encoding="utf8") as handle:
        handle.write("row\twho\tfirst\tsecond\tfirst holds\tsecond holds\n")
        handle.write("\n".join(f"{key[0]}\t{key[1]}\t{first_type}\t{second_type}\t{first_holds}\t{second_holds}"
                               for key, first_type, second_type, first_holds, second_holds in disagreements))


def parse_arguments():
    """Parse the results folder, the panel file and the optional output folder."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_folder", help="results/<coder> folder with the *.jsonl answers")
    parser.add_argument("panel_majority", help="stage1-output/panel-majority.json (first coder)")
    parser.add_argument("--out-dir", default=None,
                        help="where to write merged-positions.json and disagreements.tsv (default: results_folder)")
    return parser.parse_args()


def main():
    """Merge the answers, write the two output files and print the agreement."""
    arguments = parse_arguments()
    output_folder = arguments.out_dir or arguments.results_folder

    answers = read_answer_lines(arguments.results_folder)
    first = first_coder_positions(arguments.panel_majority)
    second = second_coder_positions(answers, arguments.results_folder)

    with open(os.path.join(output_folder, MERGED_FILE_NAME), "w", encoding="utf8") as handle:
        json.dump([second[key] for key in first if key in second], handle, ensure_ascii=False, indent=1)
    disagreements = report_agreement(first, second)
    write_disagreements(disagreements, os.path.join(output_folder, DISAGREEMENTS_FILE_NAME))
    print("disagreements written:", len(disagreements))


if __name__ == "__main__":
    main()
