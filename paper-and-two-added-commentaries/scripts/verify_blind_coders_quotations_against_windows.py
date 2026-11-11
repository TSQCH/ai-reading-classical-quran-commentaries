"""Check, after the runs, whether each blind coder's quotations occur verbatim in the served windows.

Purpose
    The source-bound design requires that the quotation a model returns for a position occur
    verbatim in the text window it was given. The blind-coding runners enforced the JSON schema
    at run time but not this content check, so it is applied here after the fact to every
    coder's output, on both sets of the SNM05 paper (624 positions of the first twelve
    commentaries, 134 positions of al-Hawwari and Himyan al-zad). The result is Table 4 of the
    paper (Section 5.4, "Quotations").

Reads
    ../../first-twelve-commentaries/second-coding-by-external-AI/data/blind-packet-*.md
    ../blind-coding/data/blind-packet-26-hawwari.md, blind-packet-27-himyan.md
        the packets: the window served for every (row, commentator).
    ../../first-twelve-commentaries/second-coding-by-external-AI/results/<coder>/*.jsonl
    ../blind-coding/results/<coder>/*.jsonl
        every coder's answers, one JSON object per position (row, who, type, holds, quote, note).
        The folder "claude" (the reference coding) and the housekeeping folders are skipped.
        A coder's answers are keyed by (row, commentator), the last line for a key winning, so a
        position answered twice is counted once (the Gemini folder of the first set holds row 4
        of al-Khazin twice); the row is read as an integer whether written as 4 or "4".

Writes
    ../blind-coding/results/Quotation-check-of-all-blind-coders.md
        one Markdown table per set: coder, positions with a quotation, verbatim, elided,
        not found, each verbatim count followed by its share of the quotations in per cent
        (rounded to the nearest whole number). Printed as well. With --date the file name
        carries a date (Quotation-check-of-all-blind-coders-<YYYY-MM-DD>.md): the date given,
        or today's when --date stands alone; the date also heads the report. Without --date
        the static name is used, so the references to the file stay valid from run to run.

Run
    python -I scripts/verify_blind_coders_quotations_against_windows.py [--out-dir FOLDER] [--date [YYYY-MM-DD]]

How a quotation is classified
    A position with type "silent" or "PARSE_ERROR", or with an empty quote, carries no
    quotation and is not counted. Otherwise, after whitespace is collapsed:
    verbatim   the quote is a substring of the window, either as written or after an
               orthographic fold (vowel marks, tatweel and invisible bidirectional controls
               removed, punctuation removed, hamza and alif forms, final ya and ta marbuta
               unified) applied to both; the fold forgives differences of spelling and
               punctuation, never of wording. The fold is the one of
               ../blind-coding/scripts/arabic_text_fold.py (since 5 Nov 2026 imported from
               there, so that this check and the runners' run-time check accept the same
               quotations; the module is identical to its copy in the first-set scripts folder);
    elided     the quote contains an ellipsis ("..." or "…") that splits it into at least two
               non-empty segments, and the segments occur (folded) in the folded window in the
               order of the quote, each found after the end of the previous one: the model
               shortened a longer passage. A segment of fewer than two words is too short to
               anchor a match (a single word occurs almost anywhere in a window), so it is left
               out of the test unless it is the only text on its side of the quote, that is the
               whole text before the first ellipsis or after the last one; a quote with fewer
               than two segments left is not elided;
    not found  anything else: the model paraphrased, re-vocalised beyond the fold, or invented.
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys

PAPER_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_FOLDER = os.path.dirname(PAPER_FOLDER)  # the repository root (named after the authors' working folder)
FIRST_SET_FOLDER = os.path.join(CLAUDE_FOLDER, "first-twelve-commentaries", "second-coding-by-external-AI")
OMAN_FOLDER = os.path.join(PAPER_FOLDER, "blind-coding")
# The orthographic fold shared with the runners (the Oman copy of arabic_text_fold.py); `python -I` does not
# put script folders on sys.path, so the folder is added here.
sys.path.insert(0, os.path.join(OMAN_FOLDER, "scripts"))
from arabic_text_fold import fold, quotation_occurs  # noqa: E402  (import after the path insert)
SETS = (  # (label, packets glob, results folder)
    ("First twelve commentaries, 624 positions", os.path.join(FIRST_SET_FOLDER, "data", "blind-packet-*.md"),
     os.path.join(FIRST_SET_FOLDER, "results")),
    ("al-Hawwari and Himyan al-zad, 134 positions", os.path.join(OMAN_FOLDER, "data", "blind-packet-2[67]-*.md"),
     os.path.join(OMAN_FOLDER, "results")),
)
DEFAULT_OUTPUT_FOLDER = os.path.join(OMAN_FOLDER, "results")
REPORT_NAME = "Quotation-check-of-all-blind-coders.md"
DATED_REPORT_NAME = "Quotation-check-of-all-blind-coders-{date:%Y-%m-%d}.md"
DATE_ARGUMENT_FORMAT = "%Y-%m-%d"  # the form of the --date value
MINIMUM_SEGMENT_WORDS = 2  # a shorter segment of an elided quotation anchors nothing unless it is alone on its side
SKIPPED_FOLDERS = ("claude", "previous-versions", "logs")
NO_QUOTATION_TYPES = ("silent", "PARSE_ERROR")
# Display names and order of the coders in the table
CODER_NAMES = (("gemini", "Gemini 3 Pro"), ("qwen", "Qwen3 14B"), ("gemma", "Gemma 3 12B"),
               ("deepseek", "DeepSeek-R1 14B"), ("fanar", "Fanar 9B"), ("llama", "Llama 3.1 8B"),
               ("falcon", "Falcon-H1 7B"), ("acegpt", "AceGPT-v2 8B"), ("allam", "ALLaM 7B"), ("jais", "Jais 13B"))

PACKET_HEADER = re.compile(r"^## (\d+) \| (.+?) \| (.+?) \| (\w+)\s*$")
ELLIPSIS = re.compile(r"\.\.\.|…")


def read_windows(packets_glob):
    """Return {(row, who): window text} from the packets; a later packet overrides an earlier one."""
    windows = {}
    for path in sorted(glob.glob(packets_glob)):
        current_key, lines = None, []
        with open(path, encoding="utf8") as packet_file:
            for line in packet_file:
                header = PACKET_HEADER.match(line)
                if header:
                    if current_key:
                        windows[current_key] = "\n".join(lines)
                    current_key, lines = (int(header.group(1)), header.group(4)), []
                elif current_key and not line.startswith("views:"):
                    lines.append(line.rstrip("\n"))
        if current_key:
            windows[current_key] = "\n".join(lines)
    return windows


def elision_segments(quote):
    """Return the folded segments of a quote that an elision test must find, in the order of the quote.

    The quote is split on its ellipses before folding, because the fold turns an ellipsis into
    a space. Empty segments are dropped. A segment of fewer than MINIMUM_SEGMENT_WORDS words is
    dropped too, unless it is the first or the last segment (the only text on its side of the
    quote), where it still has to be found.
    """
    segments = [fold(segment) for segment in ELLIPSIS.split(quote)]
    segments = [segment for segment in segments if segment]
    return [segment for index, segment in enumerate(segments)
            if len(segment.split()) >= MINIMUM_SEGMENT_WORDS or index in (0, len(segments) - 1)]


def segments_occur_in_order(segments, folded_window):
    """Return True when every segment occurs in the folded window, each after the end of the previous match."""
    search_from = 0
    for segment in segments:
        found_at = folded_window.find(segment, search_from)
        if found_at < 0:
            return False
        search_from = found_at + len(segment)
    return True


def classify(quote, window):
    """Return 'verbatim', 'elided' or 'not found' for one quotation against its window."""
    if quotation_occurs(quote, window):
        return "verbatim"
    segments = elision_segments(quote)
    if len(segments) >= 2 and segments_occur_in_order(segments, fold(window)):
        return "elided"
    return "not found"


def position_key(row, who, source):
    """Return the key (int(row), who) of one record; stop with a clear message when the row is not an integer."""
    if isinstance(row, bool) or not isinstance(row, (int, str)) or (isinstance(row, str) and not row.strip().isdigit()):
        raise ValueError(f"{source}: row {row!r} is not an integer")
    return int(row), who


def read_answers(results_folder):
    """Return {(row, who): answer} from a coder's *.jsonl files, files in name order, the last line for a key winning."""
    answers = {}
    for path in sorted(glob.glob(os.path.join(results_folder, "*.jsonl"))):
        with open(path, encoding="utf8") as answers_file:
            for line_number, line in enumerate(answers_file, 1):
                if not line.startswith("{"):
                    continue  # prose or code fences around an API answer
                try:
                    answer = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line kept as the model wrote it; the comparison scripts skip it too
                answers[position_key(answer.get("row"), answer.get("who"), f"{path} line {line_number}")] = answer
    return answers


def check_coder(results_folder, windows):
    """Count a coder's quotations by class, one per position; return (quoted, verbatim, elided, not_found)."""
    counts = {"verbatim": 0, "elided": 0, "not found": 0}
    for key, answer in read_answers(results_folder).items():
        quote = answer.get("quote") or ""
        if answer.get("type") in NO_QUOTATION_TYPES or not quote:
            continue
        if key not in windows:
            raise SystemExit(f"{results_folder}: no window was served for row {key[0]}, {key[1]}")
        counts[classify(quote, windows[key])] += 1
    return sum(counts.values()), counts["verbatim"], counts["elided"], counts["not found"]


def build_report(report_date):
    """Return the Markdown report for both sets, headed with the report date."""
    lines = [f"# Quotation check of all blind coders ({report_date:%d %b %Y})", "",
             "A quotation is verbatim when it occurs in the served window as written or after an "
             "orthographic fold, elided when it is shortened with an ellipsis and the segments around the "
             "ellipsis occur in the window in the order of the quote (a segment of one word counts only when it "
             "is the whole text on its side of the quote), and not found otherwise. Positions coded silent or in "
             "parse error carry no quotation.", ""]
    for label, packets_glob, results_root in SETS:
        windows = read_windows(packets_glob)
        if not windows:
            raise SystemExit(f"{label}: no packet matches {packets_glob}; build packets 26 and 27 first (README, steps 6 and 7)")
        lines += [f"## {label}", "", "| Coder | Quotations | Verbatim | Elided | Not found |", "|---|---|---|---|---|"]
        for slug, name in CODER_NAMES:
            folder = os.path.join(results_root, slug)
            if slug in SKIPPED_FOLDERS or not os.path.isdir(folder):
                continue
            quoted, verbatim, elided, not_found = check_coder(folder, windows)
            share = f" ({round(100 * verbatim / quoted)} %)" if quoted else ""
            lines.append(f"| {name} | {quoted} | {verbatim}{share} | {elided} | {not_found} |")
        lines.append("")
    return "\n".join(lines)


def parse_date(text):
    """Return the date written as YYYY-MM-DD, for the --date argument."""
    return datetime.datetime.strptime(text, DATE_ARGUMENT_FORMAT).date()


def main():
    """Write and print the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_FOLDER, help="folder for the report")
    parser.add_argument("--date", nargs="?", const=datetime.date.today(), default=None, type=parse_date,
                        metavar="YYYY-MM-DD",
                        help="put this date (today's when no value is given) in the report's file name")
    arguments = parser.parse_args()
    report_date = arguments.date or datetime.date.today()
    report = build_report(report_date)
    report_name = DATED_REPORT_NAME.format(date=report_date) if arguments.date else REPORT_NAME
    path = os.path.join(arguments.out_dir, report_name)
    with open(path, "w", encoding="utf8") as report_file:
        report_file.write(report)
    print(report)
    print("written", path)


if __name__ == "__main__":
    main()
