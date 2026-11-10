"""Code the Oman packets (26-27, al-Hawwari and Himyan al-zad) with Gemini through the Gemini CLI.

Purpose
    Runs every packet in data/ through Gemini non-interactively (`gemini -p`), one packet per
    call, and saves the model's JSON Lines answer. This is the Gemini 3 Pro coder of the SNM05
    paper (Section 4.2 The blind coders; results in Table 2). A packet whose saved answer has
    fewer lines than positions is run again on the next start, up to three attempts per run;
    a call that exceeds the timeout counts as a failed attempt and is retried the same way.

Reads
    Blind-coding-prompt-for-external-AI-coder-v02.md   the written coding rule; the part after
                                                       the first "---" line is sent as instructions.
                                                       The JQS runner (../../first-twelve-commentaries/
                                                       second-coding-by-external-AI/
                                                       scripts/run_blind_coding_through_gemini_cli.py)
                                                       reads v01 of the same prompt. The only
                                                       differences between v01 and v02: the phrase
                                                       "medieval Sunni commentators" (v01) is replaced
                                                       by "classical Qur'an commentators" (v02), and
                                                       the two commentator codes hawwari and himyan
                                                       are added to the list of codes; the rule text
                                                       is identical.
    data/blind-packet-*.md                             the packets (one "## row | ..." header per position)
    The Gemini CLI (npm install -g @google/gemini-cli), logged in once interactively with
    `gemini`: found as `gemini` on the PATH, or, on Windows only, at %APPDATA%\\npm\\gemini.cmd.
    No API key is read by this script: the CLI holds its own login.

Writes
    results/gemini/blind-packet-<NN>-<who>.jsonl           one JSON line per position, with the
                                                           key "verification" added (see below)
    results/gemini/blind-packet-<NN>-<who>.jsonl.incomplete.txt
                                                           stdout and stderr of the last attempt when all
                                                           three attempts returned too few lines or timed out

Run (from the blind-coding folder)
    python -I scripts/run_blind_coding_through_gemini_cli.py [model]
    model: the Gemini CLI model name; default gemini-3-pro-preview, the model of the published
    runs (recorded in ../../first-twelve-commentaries/second-coding-by-external-AI/
    results/Gemini-second-coding-results-and-three-coder-agreement-2026-11-02.md and cited as
    Gemini 3 Pro in the paper).
    Afterwards: python -I scripts/compare_oman_coders_against_claude_reference.py

Content verification (added 5 Nov 2026, after the runs reported in the paper)
    The runs the paper reports saved the model's lines as they came. Since 5 Nov 2026, once a
    packet's answer has one line per position, every parsed line is checked against the packet
    (parsed with the packet builders' header regex): row and who must name a position of the
    packet, every id in holds must be a candidate view id of that position or "OTHER", and the
    quote must occur in the served window as written or after the orthographic fold of
    arabic_text_fold.py (the module beside this script, identical to the copy in the JQS
    folder and to what the verifier applies: vowel marks, tatweel, bidirectional controls and
    punctuation removed, hamza/alif forms, final ya and ta marbuta unified, whitespace
    collapsed); an empty quote fails unless the type is silent (a commentator who says nothing
    has nothing to quote). The record is written with the key "verification": the list of
    failed checks ("row", "who", "position", "holds", "quote"; empty when all pass). The
    service runners
    only flag: a packet is not sent again for a content failure (the local Ollama runners flag
    and retry the position once). The records of the published runs do not have this key.
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

BLIND_CODING_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKETS_GLOB = os.path.join(BLIND_CODING_FOLDER, "data", "blind-packet-*.md")
RULE_PATH = os.path.join(BLIND_CODING_FOLDER, "Blind-coding-prompt-for-external-AI-coder-v02.md")
OUTPUT_FOLDER = os.path.join(BLIND_CODING_FOLDER, "results", "gemini")
GEMINI_CLI_COMMAND = "gemini"
WINDOWS_NPM_GEMINI_CMD = ("npm", "gemini.cmd")  # under %APPDATA%, where npm -g installs on Windows
# The model of the published runs (Gemini 3 Pro in the paper; model id recorded in the JQS results note of 2 Nov 2026).
DEFAULT_MODEL = "gemini-3-pro-preview"

ATTEMPTS_PER_PACKET = 3
CALL_TIMEOUT_SECONDS = 1800
PAUSE_BETWEEN_ATTEMPTS_SECONDS = 30
STDERR_TAIL_CHARACTERS = 300  # how much of a failed call's stderr is shown
INCOMPLETE_SUFFIX = ".incomplete.txt"
TIMEOUT_NOTE = "every attempt timed out after {seconds} s; no output was captured"

CLI_PROMPT = ("The piped input begins with your instructions, followed by a line reading PACKET and the packet to code. "
              "Carry out the instructions on that packet exactly. Output nothing but the JSON Lines, one line per position, "
              "every position in the packet.")
PACKET_SEPARATOR = "\n\n==== PACKET ====\n\n"
POSITION_HEADER_PATTERN = re.compile(r"^## \d+ \|", re.M)

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


def load_rule_text():
    """Return the rule: the text after the first "---" line of the prompt file (the part above it is for a human)."""
    return read_text(RULE_PATH).split("\n---\n", 1)[1].strip()


def find_gemini_cli():
    """Return the path of the Gemini CLI: `gemini` on the PATH first, else (Windows only) %APPDATA%\\npm\\gemini.cmd."""
    found = shutil.which(GEMINI_CLI_COMMAND)
    if found:
        return found
    if os.name == "nt" and os.environ.get("APPDATA"):
        fallback = os.path.join(os.environ["APPDATA"], *WINDOWS_NPM_GEMINI_CMD)
        if os.path.exists(fallback):
            return fallback
    raise SystemExit("Gemini CLI not found: install it with `npm install -g @google/gemini-cli` and sign in once with `gemini`")


def json_lines(text):
    """Return the stripped lines of a model answer that start with "{", i.e. its JSON Lines, prose dropped."""
    return [line.strip() for line in text.splitlines() if line.strip().startswith("{")]


def ask_gemini_cli(gemini_cli, model, rule_text, packet_text):
    """Run the Gemini CLI non-interactively on one packet and return the CompletedProcess (stdout holds the answer)."""
    return subprocess.run([gemini_cli, "-m", model, "-p", CLI_PROMPT],
                          input=rule_text + PACKET_SEPARATOR + packet_text, capture_output=True, text=True,
                          encoding="utf8", cwd=BLIND_CODING_FOLDER, timeout=CALL_TIMEOUT_SECONDS)


def run_packet(gemini_cli, packet_path, model, rule_text):
    """Send one packet to Gemini until the answer has one line per position; save it, or the raw output if it never does.

    A call that exceeds CALL_TIMEOUT_SECONDS is reported and counts as one failed attempt. An
    accepted answer is annotated with the failed content checks (annotate_answers) before it is
    saved; a content failure does not cause another attempt.
    """
    target_path = os.path.join(OUTPUT_FOLDER, os.path.basename(packet_path).replace(".md", ".jsonl"))
    packet_text = read_text(packet_path)
    expected_lines = len(POSITION_HEADER_PATTERN.findall(packet_text))
    positions = packet_positions(packet_text)
    if os.path.exists(target_path) and len(json_lines(read_text(target_path))) >= expected_lines:
        return
    completed = None  # the last attempt that returned, kept for the .incomplete.txt record
    for attempt in range(ATTEMPTS_PER_PACKET):
        print(os.path.basename(packet_path), "attempt", attempt + 1, flush=True)
        try:
            completed = ask_gemini_cli(gemini_cli, model, rule_text, packet_text)
        except subprocess.TimeoutExpired:
            print("   timed out after", CALL_TIMEOUT_SECONDS, "s", flush=True)
            time.sleep(PAUSE_BETWEEN_ATTEMPTS_SECONDS)
            continue
        answer_lines = json_lines(completed.stdout)
        print("  ", len(answer_lines), "of", expected_lines, "positions",
              ("| stderr: " + completed.stderr.strip()[-STDERR_TAIL_CHARACTERS:]) if completed.returncode else "")
        if len(answer_lines) >= expected_lines:
            answer_lines, flagged, unparsable = annotate_answers(answer_lines, positions)
            print("   content checks:", flagged, "flagged,", unparsable, "unparsable", flush=True)
            with open(target_path, "w", encoding="utf8") as handle:
                handle.write("\n".join(answer_lines) + "\n")
            break
        time.sleep(PAUSE_BETWEEN_ATTEMPTS_SECONDS)
    else:
        # Every attempt fell short: keep the raw output so the failure can be read, and leave no .jsonl behind.
        record = (completed.stdout + "\n\nSTDERR:\n" + completed.stderr) if completed else TIMEOUT_NOTE.format(seconds=CALL_TIMEOUT_SECONDS)
        with open(target_path + INCOMPLETE_SUFFIX, "w", encoding="utf8") as handle:
            handle.write(record)


def main():
    """Parse the model name and run every packet in data/ through the Gemini CLI."""
    parser = argparse.ArgumentParser(description="Blind-code the Oman packets with Gemini through the Gemini CLI.")
    parser.add_argument("model", nargs="?", default=DEFAULT_MODEL, help=f"Gemini CLI model name (default: {DEFAULT_MODEL})")
    arguments = parser.parse_args()
    gemini_cli = find_gemini_cli()
    rule_text = load_rule_text()
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    for packet_path in sorted(glob.glob(PACKETS_GLOB)):
        run_packet(gemini_cli, packet_path, arguments.model, rule_text)
    print("done; now: python -I scripts/compare_oman_coders_against_claude_reference.py")


if __name__ == "__main__":
    main()
