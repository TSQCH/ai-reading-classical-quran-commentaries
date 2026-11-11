"""Run the blind coding packets through Gemini CLI, one packet per call.

Purpose
    This is how Gemini's second coding of 2 November 2026 was produced
    (model id gemini-3-pro-preview given to Gemini CLI 0.66.0; the CLI's session
    log of every packet call records the model that answered as
    gemini-3.1-pro-preview). Each packet in
    data/ is piped, together with the blind coding prompt, into
    `gemini -m <model> -p "<instruction>"` and the JSON Lines answer is saved.

Reads
    Blind-coding-prompt-for-external-AI-coder-v01.md (the part after the
        first "---" line: the prompt the coder receives). The Oman runner
        (../../../paper-and-two-added-commentaries/blind-coding/scripts/
        run_blind_coding_through_gemini_cli.py) reads v02 of the same prompt.
        The only differences between v01 and v02: the phrase "medieval Sunni
        commentators" (v01) is replaced by "classical Qur'an commentators"
        (v02), and the two commentator codes hawwari and himyan are added to
        the list of codes; the rule text is identical.
    data/blind-packet-*.md (packets 01 to 24 of 24 and 25 of 25)
    Gemini CLI, installed per user with `npm install -g @google/gemini-cli`
        and set up once by running `gemini` interactively; the published runs
        used its API-key authentication (setting security.auth.selectedType =
        gemini-api-key, the key held by the CLI), not a Google-account sign-in.
        No key is read or printed by this script.
        It is found as `gemini` on the PATH or, on Windows only, at
        %APPDATA%\\npm\\gemini.cmd.

Writes
    results/gemini/blind-packet-NN-of-24.jsonl (and -25-of-25.jsonl): the
        answer lines, one JSON object per position with the key
        "verification" added (see below), only when the answer
        holds at least as many lines as the packet has positions. A packet
        whose three attempts all fall short (or time out) gets its last
        stdout and stderr saved as <name>.jsonl.incomplete.txt for inspection
        instead.
    A packet whose .jsonl already has enough lines is skipped, so the script
    resumes after a stop.

Run (from the second-coding-by-external-AI folder)
    python -I scripts/run_blind_coding_through_gemini_cli.py [model]
    model: Gemini model id passed to `gemini -m` (default gemini-3-pro-preview,
    the model of the published run, recorded in
    results/Gemini-second-coding-results-and-three-coder-agreement-2026-11-02.md).
    Then: python -I scripts/merge_external_ai_results_and_compare.py results/gemini <panel-majority.json>

Content verification (added 5 Nov 2026, after the runs reported in the papers)
    The runs the papers report saved the model's lines as they came. Since
    5 Nov 2026, once a packet's answer has one line per position, every
    parsed line is checked against the packet (parsed with the packet
    builders' header regex): row and who must name a position of the
    packet, every id in holds must be a candidate view id of that position
    or "OTHER", and the quote must occur in the served window as written or
    after the orthographic fold of arabic_text_fold.py (the module beside
    this script, identical to the copy in the Oman blind-coding folder and
    to what the verifier applies: vowel marks, tatweel, bidirectional
    controls and punctuation removed, hamza/alif forms, final ya and ta
    marbuta unified, whitespace collapsed; an empty quote fails unless the
    type is silent, since a commentator who says nothing has nothing to
    quote). The record is written with the
    key "verification": the list of failed checks ("row", "who",
    "position", "holds", "quote"; empty when all pass). The service runners
    only flag: a packet is not sent again for a content failure (the local
    Ollama runners flag, and retry the position once only with
    --verify-at-run-time, which the published runs did not use). The records of the
    published runs do not have this key.

Working folder of the CLI
    The Gemini CLI is started in the project folder (cwd) and may list and
    read the files there. The CLI's session logs of the published run of
    2 Nov 2026 (29 packet sessions: packet 1 four times, two calls in an
    earlier layout that returned prose and two complete answers of which
    the second was kept; packet 8 twice, because its first answer numbered
    the rows 1 to 26 instead of the packet's rows and was replaced by hand;
    packets 2 to 7, 9 to 24 and 25 once each) show that the model called no
    tool and read no file; the one session with tool calls is the model-name check
    made before the runs, in which the model read this runner, the archived
    API runner and the folder's README. For a blind re-run, move results/
    out of the folder first.

Feeds
    results/gemini/*.jsonl, the Gemini column of every agreement table and
    one of the three coders in three_coders_agreement_fleiss_kappa.py.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

# The shared orthographic fold sits beside this script; `python -I` does not put the script folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arabic_text_fold import fold, quotation_occurs  # noqa: E402  (import after the path insert)

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_FILE = os.path.join(PROJECT_FOLDER, "Blind-coding-prompt-for-external-AI-coder-v01.md")
PACKETS_GLOB = os.path.join(PROJECT_FOLDER, "data", "blind-packet-*.md")
RESULTS_FOLDER = os.path.join(PROJECT_FOLDER, "results", "gemini")
GEMINI_CLI_COMMAND = "gemini"
WINDOWS_NPM_GEMINI_CMD = ("npm", "gemini.cmd")  # under %APPDATA%, where npm -g installs on Windows

# The model id of the published run of 2 Nov 2026 (recorded in the results note of that date); the
# CLI's session logs of that run record the model that answered as gemini-3.1-pro-preview.
DEFAULT_MODEL = "gemini-3-pro-preview"
CALL_TIMEOUT_SECONDS = 1800
PACKET_ATTEMPTS = 3  # a short answer (fewer lines than positions) or a timed-out call is asked for again
RETRY_WAIT_SECONDS = 30
STDERR_TAIL_CHARACTERS = 300  # how much of a failed call's stderr is shown
TIMEOUT_NOTE = "every attempt timed out after {seconds} s; no output was captured"

# The -p instruction: the prompt and the packet arrive on stdin, separated by
# the PACKET_SEPARATOR line.
CLI_INSTRUCTION = ("The piped input begins with your instructions, followed by a line reading PACKET and the packet "
                   "to code. Carry out the instructions on that packet exactly. Output nothing but the JSON Lines, "
                   "one line per position, every position in the packet.")
PACKET_SEPARATOR = "\n\n==== PACKET ====\n\n"

# One position header in a packet: "## <row> | ..."
POSITION_HEADER = re.compile(r"^## \d+ \|", re.M)

# One packet entry, as the packet builders write it: the header "## row | unit | phrase | who", a
# "views:" line, a blank line, then the served window (the builders' header regex, with the window).
PACKET_ENTRY_PATTERN = re.compile(r"## (\d+) \| ([^|]+)\| ([^|]+)\| (\w+)\n(views: [^\n]*)\n\n(.*)", re.S)
# One candidate view in the views line: "V1 = label ; V2 = label ; ..."; the id is the token before " = ".
VIEW_ID_PATTERN = re.compile(r"(?:^views: |; )\s*(\w+) = ")
OTHER_VIEW_ID = "OTHER"
SILENT_TYPE = "silent"  # the one type that may carry no quotation: a commentator who says nothing has nothing to quote
UNMATCHED_POSITION_CHECK = "position"  # the answer's row and who both occur in the packet, but not together


def packet_positions(packet_text):
    """Return {(row, who): (set of candidate view ids, served window)} for every entry of a packet."""
    positions = {}
    for entry in re.split(r"\n(?=## )", packet_text):
        match = PACKET_ENTRY_PATTERN.match(entry.strip())
        if match:
            positions[(int(match.group(1)), match.group(4))] = (set(VIEW_ID_PATTERN.findall(match.group(5))), match.group(6))
    return positions


def failed_checks(answer, positions):
    """Return the list of content checks one parsed answer fails (empty when all pass).

    The answer's row and who must name a position of the packet; when they do not, the list
    holds "row" and/or "who" for whichever value occurs nowhere in the packet, or "position"
    when both occur but not together, and the other checks cannot be made. Otherwise every id
    in holds must be a candidate view id of that position or OTHER ("holds"), and the quote must
    occur in the served window as written (whitespace collapsed) or after the orthographic fold
    of arabic_text_fold.py applied to both ("quote"; an empty quote passes only when the type is silent).
    """
    key = (answer.get("row"), answer.get("who"))
    if key not in positions:
        failed = [name for name, value, index in (("row", key[0], 0), ("who", key[1], 1))
                  if value not in {position[index] for position in positions}]
        return failed or [UNMATCHED_POSITION_CHECK]
    view_ids, window = positions[key]
    failed = []
    holds = answer.get("holds", [])
    if not isinstance(holds, list):
        holds = [holds]
    if any(str(held) not in view_ids and str(held) != OTHER_VIEW_ID for held in holds):
        failed.append("holds")
    quote = str(answer.get("quote") or "")
    quote_required = answer.get("type") != SILENT_TYPE  # only a silent position may leave the quote empty
    # Tested on the folded quote: a quote of vowel marks or punctuation only counts as empty, so
    # that it passes on a silent position (as before 7 Nov 2026) and fails on any other.
    folded_quote = fold(quote)
    if (quote_required and not folded_quote) or (folded_quote and not quotation_occurs(quote, window)):
        failed.append("quote")
    return failed


def annotate_answers(lines, positions):
    """Add "verification" (the list of failed checks) to every JSON line of a packet's answer.

    Returns (annotated lines, number of answers that failed a check, number of lines that did
    not parse). A line that does not parse as JSON is kept as it is, so that the record of what
    the model said stays complete; the comparison scripts skip it, so that its position counts
    as missing (MISSING), a disagreement in every measure.
    """
    annotated, flagged, unparsable = [], 0, 0
    for line in lines:
        try:
            answer = json.loads(line)
        except json.JSONDecodeError:
            annotated.append(line)
            unparsable += 1
            continue
        answer["verification"] = failed_checks(answer, positions)
        flagged += bool(answer["verification"])
        annotated.append(json.dumps(answer, ensure_ascii=False))
    return annotated, flagged, unparsable


def read_text(path):
    """Return the whole content of a UTF-8 text file."""
    with open(path, encoding="utf8") as handle:
        return handle.read()


def load_prompt():
    """Return the coder's prompt: the part of the prompt file after the first
    "---" line (the text above it is the instruction to the human operator)."""
    return read_text(PROMPT_FILE).split("\n---\n", 1)[1].strip()


def find_gemini_cli():
    """Return the path of the Gemini CLI: `gemini` on the PATH first, else
    (Windows only) %APPDATA%\\npm\\gemini.cmd; stop with a message if neither exists."""
    found = shutil.which(GEMINI_CLI_COMMAND)
    if found:
        return found
    if os.name == "nt" and os.environ.get("APPDATA"):
        fallback = os.path.join(os.environ["APPDATA"], *WINDOWS_NPM_GEMINI_CMD)
        if os.path.exists(fallback):
            return fallback
    raise SystemExit("Gemini CLI not found: install it with `npm install -g @google/gemini-cli` and set it up once "
                     "by running `gemini` (the published runs used an API key)")


def answer_lines(text):
    """The JSON object lines of an answer (lines starting with "{"), stripped;
    prose or code fences around them are dropped."""
    return [line.strip() for line in text.splitlines() if line.strip().startswith("{")]


def packet_is_done(target_path, expected_positions):
    """True when the saved answer already has one line per position."""
    return os.path.exists(target_path) and len(answer_lines(read_text(target_path))) >= expected_positions


def ask_gemini_cli(gemini_cli, model, prompt, packet):
    """Run Gemini CLI non-interactively on one packet and return the
    CompletedProcess (stdout holds the answer)."""
    return subprocess.run(
        [gemini_cli, "-m", model, "-p", CLI_INSTRUCTION],
        input=prompt + PACKET_SEPARATOR + packet,
        capture_output=True, text=True, encoding="utf8", cwd=PROJECT_FOLDER, timeout=CALL_TIMEOUT_SECONDS)


def code_packet(gemini_cli, packet_path, model, prompt):
    """Code one packet: up to PACKET_ATTEMPTS calls until the answer has at
    least one line per position; save the lines, or the last short answer
    with its stderr as .incomplete.txt. A call that exceeds
    CALL_TIMEOUT_SECONDS is reported and counts as one failed attempt. An
    accepted answer is annotated with the failed content checks
    (annotate_answers) before it is saved; a content failure does not cause
    another attempt."""
    target_path = os.path.join(RESULTS_FOLDER, os.path.basename(packet_path).replace(".md", ".jsonl"))
    packet = read_text(packet_path)
    expected_positions = len(POSITION_HEADER.findall(packet))
    positions = packet_positions(packet)
    if packet_is_done(target_path, expected_positions):
        return
    result = None  # the last attempt that returned, kept for the .incomplete.txt record
    for attempt in range(PACKET_ATTEMPTS):
        print(os.path.basename(packet_path), "attempt", attempt + 1, flush=True)
        try:
            result = ask_gemini_cli(gemini_cli, model, prompt, packet)
        except subprocess.TimeoutExpired:
            print("   timed out after", CALL_TIMEOUT_SECONDS, "s", flush=True)
            time.sleep(RETRY_WAIT_SECONDS)
            continue
        lines = answer_lines(result.stdout)
        stderr_note = ("| stderr: " + result.stderr.strip()[-STDERR_TAIL_CHARACTERS:]) if result.returncode else ""
        print("  ", len(lines), "of", expected_positions, "positions", stderr_note)
        if len(lines) >= expected_positions:
            lines, flagged, unparsable = annotate_answers(lines, positions)
            print("   content checks:", flagged, "flagged,", unparsable, "unparsable", flush=True)
            with open(target_path, "w", encoding="utf8") as handle:
                handle.write("\n".join(lines) + "\n")
            break
        time.sleep(RETRY_WAIT_SECONDS)
    else:
        record = (result.stdout + "\n\nSTDERR:\n" + result.stderr) if result else TIMEOUT_NOTE.format(seconds=CALL_TIMEOUT_SECONDS)
        with open(target_path + ".incomplete.txt", "w", encoding="utf8") as handle:
            handle.write(record)


def parse_arguments():
    """Parse the optional model id."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", nargs="?", default=DEFAULT_MODEL,
                        help=f"Gemini model id passed to `gemini -m` (default {DEFAULT_MODEL})")
    return parser.parse_args()


def main():
    """Code every packet in data/ that is not yet done."""
    arguments = parse_arguments()
    gemini_cli = find_gemini_cli()
    prompt = load_prompt()
    os.makedirs(RESULTS_FOLDER, exist_ok=True)
    for packet_path in sorted(glob.glob(PACKETS_GLOB)):
        code_packet(gemini_cli, packet_path, arguments.model, prompt)
    print("done; now: python -I scripts/merge_external_ai_results_and_compare.py results/gemini <panel-majority.json>")


if __name__ == "__main__":
    main()
