"""Three-coder agreement (first coder, Claude, Gemini) with Fleiss' kappa.

Purpose
    Three coders read the same positions blind: the first coder
    (panel-majority.json), Claude on 23 October 2026 and Gemini on
    2 November 2026. On the positions that all three coded (609: the 15
    positions of packet 25 have no Claude code), this script reports the
    share of positions on which all three agree and Fleiss' kappa, on the
    five types and on vote/no vote; on the positions where all three read the
    commentator as voting, the number on which they name the same view and
    Fleiss' kappa on the view, the view labels of the candidate views of each
    point being treated as pooled nominal categories, as the papers state;
    the pairwise type agreement of each two coders; and, for the 15 positions
    coded by the first coder and Gemini only, their type agreement.

    Vote/no vote: "vote" for prefers and single, "no vote" for the other
    three types, and ERROR for a PARSE_ERROR, so that a parse error never
    agrees with another coder (none of the three coders here has one).
    Same view: the SET of view ids in "holds" of each coder, compared for
    equality. The rule allows exactly one view for prefers and single, so a
    coder that lists several ids on a vote has departed from the rule and
    disagrees unless the others list the same set. Each coder's value is the
    sorted ids joined by "+" (one nominal label per position, pooled across
    points, as the papers state), so that Fleiss' kappa applies unchanged.
    Kappa (Cohen's or Fleiss') is undefined when the expected agreement is 1
    (one category only): it is then nan and printed as "n/a".

    Coverage check: the script stops with a clear message unless Gemini
    coded every position of the first coder and Claude's positions are all
    positions of the first coder, so that the positions without a Claude code
    are exactly those of packet 25 (rows 17, 19 and 63, coded after Claude's
    October run); the three-coder set is then Claude's 609 positions.

Reads
    <stage1_output>/panel-majority.json
        the first coder: one record per phrase, n = row, positions[<who>].
    <stage1_output>/independent-coding/second-coder-positions.json
        Claude's blind coding: one object per position with n, who, type, holds.
    <gemini_results>/merged-positions.json
        Gemini's blind coding merged by merge_external_ai_results_and_compare.py:
        one object per position with row, who, type, holds, quote, note.

Writes (to <out_folder>)
    three-coders-positions.tsv
        every position coded by all three: row, who, the three types and the
        three held-view lists.
    three-coders-disagreements.tsv
        the positions where the three types are not unanimous, with Gemini's
        quote and note, for the human reader who settles them. Written with
        csv.writer (tab delimiter, minimal quoting, CRLF line ends as in the
        published file), so a quote that held a tab, a quotation mark or a
        line break would be quoted instead of breaking the column layout.

Run
    python -I three_coders_agreement_fleiss_kappa.py <stage1_output> <gemini_results> <out_folder>

Feeds
    The three-coder table in
    results/Gemini-second-coding-results-and-three-coder-agreement-2026-11-02.md
    (Fleiss' kappa 0.86 on type, 0.87 on vote; where all three vote, the same
    view in 167 of 172 positions, Fleiss' kappa 0.97) and the
    corresponding sentences in the SNM05 paper and the authors' article in preparation on the first twelve commentaries.
"""

import argparse
import collections
import csv
import json
import os

# Only these two types are a vote for one view.
VOTING_TYPES = ("prefers", "single")
PARSE_ERROR_TYPE = "PARSE_ERROR"  # type written by the runners when a model's output did not satisfy the schema
VOTE_LABEL = "vote"
NO_VOTE_LABEL = "no vote"
VOTE_ERROR_LABEL = "ERROR"  # vote category of a parse error: equal to neither "vote" nor "no vote"
VIEW_ID_SEPARATOR = "+"  # joins the sorted view ids of one vote into one nominal label, e.g. "a+b"
UNDEFINED_KAPPA_TEXT = "n/a"  # printed where kappa has no denominator (one category only)
PACKET_25_ROWS = (17, 19, 63)  # the rows of packet 25, coded after Claude's October run: no Claude code
TSV_LINE_TERMINATOR = "\r\n"  # the line ends of the published TSV files (written on Windows)

PANEL_MAJORITY_FILE = "panel-majority.json"
CLAUDE_CODING_FILE = os.path.join("independent-coding", "second-coder-positions.json")
GEMINI_MERGED_FILE = "merged-positions.json"
POSITIONS_TSV = "three-coders-positions.tsv"
DISAGREEMENTS_TSV = "three-coders-disagreements.tsv"


def load_json(path):
    """Return the parsed content of a UTF-8 JSON file."""
    with open(path, encoding="utf8") as handle:
        return json.load(handle)


def position_key(row, who, source):
    """Return the key (int(row), who) of one record; stop with a clear message when the row is not an integer."""
    if isinstance(row, bool) or not isinstance(row, (int, str)) or (isinstance(row, str) and not row.strip().isdigit()):
        raise ValueError(f"{source}: row {row!r} is not an integer")
    return int(row), who


def first_coder_positions(stage1_output):
    """Return {(int(row), who): position} from the first coder's panel file (n = row)."""
    path = os.path.join(stage1_output, PANEL_MAJORITY_FILE)
    return {position_key(record["n"], who, path): position
            for record in load_json(path) for who, position in record["positions"].items()}


def claude_positions(stage1_output):
    """Return {(int(row), who): code} from Claude's blind coding (key n)."""
    path = os.path.join(stage1_output, CLAUDE_CODING_FILE)
    return {position_key(code["n"], code["who"], path): code for code in load_json(path)}


def gemini_positions(gemini_results):
    """Return {(int(row), who): code} from Gemini's merged answers (key row)."""
    path = os.path.join(gemini_results, GEMINI_MERGED_FILE)
    return {position_key(code["row"], code["who"], path): code for code in load_json(path)}


def fleiss_kappa(ratings):
    """Fleiss' kappa for a list of positions, each a list of one category per coder.

    For each position i with n coders and n_ij coders choosing category j,
    the agreement P_i = (sum_j n_ij^2 - n) / (n (n - 1)) is the share of coder
    pairs that agree. P_bar is the mean of P_i over the positions. The expected
    agreement P_e = sum_j p_j^2, where p_j is the share of all ratings that
    fall in category j. kappa = (P_bar - P_e) / (1 - P_e); nan when there
    are no positions, and nan when P_e is 1 (every rating in one category, so
    the formula has no denominator and kappa is undefined).
    """
    if not ratings:
        return float("nan")
    coders_per_position = len(ratings[0])
    categories = sorted(set(category for position in ratings for category in position))
    agreement_per_position = []
    ratings_per_category = collections.Counter()
    for position in ratings:
        counts = collections.Counter(position)
        ratings_per_category.update(counts)
        agreement_per_position.append(
            (sum(count * count for count in counts.values()) - coders_per_position)
            / (coders_per_position * (coders_per_position - 1)))
    mean_agreement = sum(agreement_per_position) / len(ratings)
    total_ratings = len(ratings) * coders_per_position
    expected_agreement = sum((ratings_per_category[category] / total_ratings) ** 2 for category in categories)
    if expected_agreement >= 1:
        return float("nan")
    return (mean_agreement - expected_agreement) / (1 - expected_agreement)


def format_kappa(kappa):
    """kappa with two decimals, or "n/a" when it is nan (undefined)."""
    return UNDEFINED_KAPPA_TEXT if kappa != kappa else f"{kappa:.2f}"


def vote_label(code_type):
    """The vote category of a position type: "vote", "no vote", or ERROR for a parse error."""
    if code_type == PARSE_ERROR_TYPE:
        return VOTE_ERROR_LABEL
    return VOTE_LABEL if code_type in VOTING_TYPES else NO_VOTE_LABEL


def held_views(code):
    """The list of view ids a coder holds, each as text (empty when the key is absent or null)."""
    return [str(view_id) for view_id in code.get("holds") or []]


def view_label(code):
    """The sorted held view ids joined by "+", one nominal label for the
    same-view comparison: a vote holds one id under the rule, so a coder that
    lists several ids gets a label such as "a+b" that equals another coder's
    only when he lists the same set. Empty "holds" gives ""."""
    return VIEW_ID_SEPARATOR.join(sorted(held_views(code)))


def unanimous_count(ratings):
    """How many positions have the same code from every coder."""
    return sum(len(set(position)) == 1 for position in ratings)


def report_agreement(first, claude, gemini, three_coder_keys):
    """Print the Fleiss' kappa figures on type, vote and view, the same-view
    count and the pairwise type agreement for the positions coded by all three."""
    type_ratings = [[first[key]["type"], claude[key]["type"], gemini[key]["type"]] for key in three_coder_keys]
    vote_ratings = [[vote_label(code_type) for code_type in position] for position in type_ratings]
    unanimous_type = unanimous_count(type_ratings)
    unanimous_vote = unanimous_count(vote_ratings)
    print(f"positions with three codes: {len(three_coder_keys)}")
    print(f"type: all three agree {unanimous_type} ({100*unanimous_type/len(type_ratings):.1f}%), "
          f"Fleiss kappa {format_kappa(fleiss_kappa(type_ratings))}")
    print(f"vote/no vote: all three agree {unanimous_vote} ({100*unanimous_vote/len(vote_ratings):.1f}%), "
          f"Fleiss kappa {format_kappa(fleiss_kappa(vote_ratings))}")

    # Where all three read the commentator as voting: do they name the same view? The view
    # labels (e.g. "a", "b", or "a+b" for a coder that listed two) of every point are pooled
    # as nominal categories for Fleiss' kappa.
    view_ratings = [[view_label(first[key]), view_label(claude[key]), view_label(gemini[key])]
                    for key in three_coder_keys
                    if all(code_type in VOTING_TYPES
                           for code_type in (first[key]["type"], claude[key]["type"], gemini[key]["type"]))]
    print(f"all three vote: {len(view_ratings)} positions, same view in {unanimous_count(view_ratings)}, "
          f"Fleiss kappa {format_kappa(fleiss_kappa(view_ratings))}")

    def pairwise_type_agreement(coder_a, coder_b):
        """Positions on which two coders gave the same type."""
        return sum(coder_a[key]["type"] == coder_b[key]["type"] for key in three_coder_keys)

    print(f"pairwise type agreement: first-Claude {pairwise_type_agreement(first, claude)}, "
          f"first-Gemini {pairwise_type_agreement(first, gemini)}, "
          f"Claude-Gemini {pairwise_type_agreement(claude, gemini)} of {len(three_coder_keys)}")


def write_positions_tsv(first, claude, gemini, three_coder_keys, output_path):
    """Write one line per three-coder position: the three types and held views."""
    with open(output_path, "w", encoding="utf8") as handle:
        handle.write("row\twho\tfirst\tclaude\tgemini\tfirst_holds\tclaude_holds\tgemini_holds\n")
        for key in three_coder_keys:
            handle.write("\t".join([
                str(key[0]), key[1], first[key]["type"], claude[key]["type"], gemini[key]["type"],
                ",".join(held_views(first[key])), ",".join(held_views(claude[key])), ",".join(held_views(gemini[key])),
            ]) + "\n")


def write_disagreements_tsv(first, claude, gemini, three_coder_keys, output_path):
    """Write the positions whose three types are not unanimous, with Gemini's
    quote and note so that the human reader can see what Gemini saw.
    csv.writer with minimal quoting keeps the columns intact if a quote or note
    ever holds a tab, a quotation mark or a line break."""
    with open(output_path, "w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", quoting=csv.QUOTE_MINIMAL, lineterminator=TSV_LINE_TERMINATOR)
        writer.writerow(["row", "who", "first", "claude", "gemini", "gemini_quote", "gemini_note"])
        for key in three_coder_keys:
            if len({first[key]["type"], claude[key]["type"], gemini[key]["type"]}) > 1:
                writer.writerow([
                    key[0], key[1], first[key]["type"], claude[key]["type"], gemini[key]["type"],
                    gemini[key].get("quote", ""), gemini[key].get("note", ""),
                ])


def check_coverage(first, claude, gemini):
    """Stop with a clear message unless the three codings cover the positions as published.

    Gemini must have coded every position of the first coder, every Claude position must be
    a position of the first coder, and the first-coder positions without a Claude code must
    all lie in packet 25 (PACKET_25_ROWS). The three-coder set is then exactly Claude's
    positions (609 in the published run) and no position is dropped silently.
    """
    missing_from_gemini = sorted(key for key in first if key not in gemini)
    if missing_from_gemini:
        raise SystemExit(
            f"{len(missing_from_gemini)} first-coder positions have no Gemini code: {missing_from_gemini[:10]}")
    unknown_to_first = sorted(key for key in claude if key not in first)
    if unknown_to_first:
        raise SystemExit(
            f"{len(unknown_to_first)} Claude positions are not positions of the first coder: {unknown_to_first[:10]}")
    missing_from_claude = sorted(key for key in first if key not in claude)
    outside_packet_25 = [key for key in missing_from_claude if key[0] not in PACKET_25_ROWS]
    if outside_packet_25:
        raise SystemExit(
            f"{len(outside_packet_25)} first-coder positions outside packet 25 (rows {PACKET_25_ROWS}) "
            f"have no Claude code: {outside_packet_25[:10]}")


def parse_arguments():
    """Parse the three positional folders."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage1_output", help="twelve-commentaries/stage1-output (first coder and Claude's coding)")
    parser.add_argument("gemini_results", help="results/gemini folder with merged-positions.json")
    parser.add_argument("out_folder", help="folder that receives the two TSV files")
    return parser.parse_args()


def main():
    """Load the three codings, print the agreement and write the two TSV files."""
    arguments = parse_arguments()
    first = first_coder_positions(arguments.stage1_output)
    claude = claude_positions(arguments.stage1_output)
    gemini = gemini_positions(arguments.gemini_results)
    check_coverage(first, claude, gemini)

    three_coder_keys = [key for key in first if key in claude and key in gemini]
    report_agreement(first, claude, gemini, three_coder_keys)
    write_positions_tsv(first, claude, gemini, three_coder_keys, os.path.join(arguments.out_folder, POSITIONS_TSV))
    write_disagreements_tsv(first, claude, gemini, three_coder_keys, os.path.join(arguments.out_folder, DISAGREEMENTS_TSV))

    # Packet 25 (rows 17, 19, 63 of the extended commentators) was coded after
    # Claude's October run, so those positions have only two codes.
    two_coder_keys = [key for key in first if key in gemini and key not in claude]
    two_coder_agree = sum(first[key]["type"] == gemini[key]["type"] for key in two_coder_keys)
    print(f"positions with first coder and Gemini only (no Claude code): {len(two_coder_keys)}, type agree {two_coder_agree}")


if __name__ == "__main__":
    main()
