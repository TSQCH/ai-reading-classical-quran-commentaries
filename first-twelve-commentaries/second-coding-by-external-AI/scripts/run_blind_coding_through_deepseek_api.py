"""Run the 25 blind coding packets through the DeepSeek API, one packet per call.

Purpose
    Sends each packet in data/ to DeepSeek's OpenAI-compatible chat
    completions endpoint with the blind coding prompt as system message and
    saves the JSON Lines answer, so that the DeepSeek frontier model can be
    compared with the first coder like Gemini (this is the hosted DeepSeek
    API; the local DeepSeek-R1-Distill run is in
    run_blind_coding_through_local_ollama_models.py).

Reads
    Blind-coding-prompt-for-external-AI-coder-v01.md (the part after the
        first "---" line: the prompt the coder receives)
    data/blind-packet-*.md (packets 01 to 24 of 24 and 25 of 25)
    API key: the environment variable DEEPSEEK_API_KEY if it is set, otherwise
        the first line of DeepSeek-API-Key.txt in a _secrets folder beside the
        three folders of the deposit, two levels above this project folder
        (../../_secrets from second-coding-by-external-AI; key made at
        https://platform.deepseek.com/api_keys). The key is never printed.

Writes
    results/deepseek-api/blind-packet-NN-of-24.jsonl (and -25-of-25.jsonl): the
        answer lines, one JSON object per position with the key
        "verification" added (see below), only when the answer
        holds at least as many lines as the packet has positions. A packet
        whose three attempts all fall short gets its last answer saved as
        <name>.jsonl.incomplete.txt for inspection instead.
    A packet whose .jsonl already has enough lines is skipped, so the script
    resumes after a stop.

Run (from the second-coding-by-external-AI folder)
    python -I scripts/run_blind_coding_through_deepseek_api.py [model]
    model: deepseek-reasoner (thinking, default) or deepseek-chat.
    Then: python -I scripts/merge_external_ai_results_and_compare.py results/deepseek-api <panel-majority.json>

Content verification (added 5 Nov 2026)
    The DeepSeek API runs are not reported in the papers; they saved the model's lines as they came. Since
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
    runs of before 5 Nov 2026 do not have this key.

Feeds
    results/deepseek-api/*.jsonl, compared by merge_external_ai_results_and_compare.py.
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request

# The shared orthographic fold sits beside this script; `python -I` does not put the script folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arabic_text_fold import fold, quotation_occurs  # noqa: E402  (import after the path insert)

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_FOLDER = os.path.join(os.path.dirname(os.path.dirname(PROJECT_FOLDER)), "_secrets")
SECRETS_FILE = os.path.join(SECRETS_FOLDER, "DeepSeek-API-Key.txt")
KEY_ENVIRONMENT_VARIABLE = "DEEPSEEK_API_KEY"

PROMPT_FILE = os.path.join(PROJECT_FOLDER, "Blind-coding-prompt-for-external-AI-coder-v01.md")
PACKETS_GLOB = os.path.join(PROJECT_FOLDER, "data", "blind-packet-*.md")
RESULTS_FOLDER = os.path.join(PROJECT_FOLDER, "results", "deepseek-api")  # never the folder of the local DeepSeek-R1 run

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-reasoner"
MODEL_CHOICES = ("deepseek-reasoner", "deepseek-chat")
TEMPERATURE = 0
MAX_TOKENS = 16000  # 26 positions with quotes fit well within this
REQUEST_TIMEOUT_SECONDS = 1800  # the reasoner thinks for minutes on a packet
REQUEST_RETRIES = 4  # network or server errors: wait 30, 60, 90, 120 s between tries
RETRY_WAIT_SECONDS = 30
PACKET_ATTEMPTS = 3  # a short answer (fewer lines than positions) is asked for again

USER_MESSAGE_PREFIX = ("The packet file follows. Output nothing but the JSON Lines, one line per position, "
                       "every position in the packet.\n\n")

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


def load_api_key():
    """Return the API key from the environment variable, else from the secrets file."""
    key = os.environ.get(KEY_ENVIRONMENT_VARIABLE)
    if key:
        return key.strip()
    with open(SECRETS_FILE, encoding="utf8") as handle:
        return handle.readline().strip()


def ask_deepseek(model, api_key, prompt, packet):
    """Send one packet to the model and return the answer text.

    Retries REQUEST_RETRIES times with a growing wait on any error (timeout,
    HTTP 5xx, rate limit); only the error text is printed, never the key.
    Stops the script after the last failed try.
    """
    body = {"model": model, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": USER_MESSAGE_PREFIX + packet}]}
    for try_number in range(REQUEST_RETRIES):
        try:
            request = urllib.request.Request(
                API_URL, data=json.dumps(body).encode("utf8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key})
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.load(response)["choices"][0]["message"]["content"]
        except Exception as error:
            print("  retry", try_number + 1, error)
            time.sleep(RETRY_WAIT_SECONDS * (try_number + 1))
    raise SystemExit("gave up")


def answer_lines(text):
    """The JSON object lines of an answer (lines starting with "{"), stripped;
    prose or code fences around them are dropped."""
    return [line.strip() for line in text.splitlines() if line.strip().startswith("{")]


def packet_is_done(target_path, expected_positions):
    """True when the saved answer already has one line per position."""
    return os.path.exists(target_path) and len(answer_lines(read_text(target_path))) >= expected_positions


def code_packet(packet_path, model, api_key, prompt):
    """Code one packet: up to PACKET_ATTEMPTS calls until the answer has at
    least one line per position; save the lines, or the last short answer as
    .incomplete.txt. An accepted answer is annotated with the failed content
    checks (annotate_answers) before it is saved; a content failure does not
    cause another attempt."""
    target_path = os.path.join(RESULTS_FOLDER, os.path.basename(packet_path).replace(".md", ".jsonl"))
    packet = read_text(packet_path)
    expected_positions = len(POSITION_HEADER.findall(packet))
    positions = packet_positions(packet)
    if packet_is_done(target_path, expected_positions):
        return
    for attempt in range(PACKET_ATTEMPTS):
        print(os.path.basename(packet_path), "attempt", attempt + 1, flush=True)
        answer = ask_deepseek(model, api_key, prompt, packet)
        lines = answer_lines(answer)
        print("  ", len(lines), "of", expected_positions, "positions")
        if len(lines) >= expected_positions:
            lines, flagged, unparsable = annotate_answers(lines, positions)
            print("   content checks:", flagged, "flagged,", unparsable, "unparsable", flush=True)
            with open(target_path, "w", encoding="utf8") as handle:
                handle.write("\n".join(lines) + "\n")
            break
    else:
        with open(target_path + ".incomplete.txt", "w", encoding="utf8") as handle:
            handle.write(answer)


def parse_arguments():
    """Parse the optional model name."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", nargs="?", default=DEFAULT_MODEL, choices=MODEL_CHOICES,
                        help=f"DeepSeek model, one of {', '.join(MODEL_CHOICES)} (default {DEFAULT_MODEL})")
    return parser.parse_args()


def main():
    """Code every packet in data/ that is not yet done."""
    arguments = parse_arguments()
    api_key = load_api_key()
    prompt = load_prompt()
    os.makedirs(RESULTS_FOLDER, exist_ok=True)
    for packet_path in sorted(glob.glob(PACKETS_GLOB)):
        code_packet(packet_path, arguments.model, api_key, prompt)
    print("done; now: python -I scripts/merge_external_ai_results_and_compare.py results/deepseek-api <panel-majority.json>")


if __name__ == "__main__":
    main()
