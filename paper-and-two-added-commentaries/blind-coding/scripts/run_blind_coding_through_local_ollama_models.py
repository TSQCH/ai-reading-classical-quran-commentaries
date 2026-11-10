"""Code the 134 Oman positions (packets 26-27) with open-weight models served by Ollama.

Purpose
    Runs the blind coding of al-Hawwari and Himyan al-zad (packets 26 and 27, 67 positions
    each) through the nine open-weight models of the SNM05 paper, one position per call, at
    temperature zero and with the output constrained to a JSON schema (paper Sections 3.6
    Implementation and 4.2 The blind coders; results in Table 2). The models are served by an
    Ollama server; by default the one on this PC, or the one OLLAMA_URL names. Runs are
    resumable: positions already in the output file are skipped, and the output file is re-read
    before every call, so a watchdog can restart the script after an interruption and several
    machines can share one model's run on one file (one forward, one --reverse).

Reads
    Blind-coding-prompt-for-external-AI-coder-v02.md   the written coding rule; the part after
                                                       the first "---" line is the system prompt
    data/blind-packet-*.md                             the packets, one "## row | unit | phrase | who"
                                                       entry per position
    OLLAMA_URL (environment variable, optional)        base URL of the Ollama server;
                                                       default http://localhost:11434 (a server on
                                                       this PC). The runs of 4 Nov 2026 used a
                                                       server on another office PC, for example
                                                       OLLAMA_URL=http://ollama-server.example:11434
                                                       (a placeholder name; put the server's
                                                       own address).
    No API key is needed: Ollama is a local server without authentication.

Writes
    results/<slug>/positions.jsonl   one JSON object per position, appended as coded:
                                     row, who, type, holds, quote, note, seconds (wall-clock),
                                     verification (see below)
                                     type is "PARSE_ERROR" when the model's answer was not JSON
                                     on either attempt
    results/<slug>/model-info.json   the model tag, citation name, quantisation and call options

Run (from the blind-coding folder)
    python -I scripts/run_blind_coding_through_local_ollama_models.py <slug> [<slug> ...]
    python -I scripts/run_blind_coding_through_local_ollama_models.py all
    Options: --limit N    stop after N positions in total (test run)
             --reverse    code from the last position backwards, so that a second machine can
                          share one model's run from the other end
             --verify-at-run-time
                          retry a position once when its parsed answer fails a content check
                          (see below); off by default
    Slugs: allam, fanar, llama, qwen, gemma, deepseek, acegpt, falcon, jais (see MODELS).
    The models are pulled separately (ollama pull ...); the script waits until a model is present.
    Afterwards: python -I scripts/compare_oman_coders_against_claude_reference.py

Content verification (added 5 Nov 2026, after the runs reported in the paper)
    The runs of 4 Nov 2026 that the paper reports enforced the JSON schema only, with one
    re-ask when an answer was not valid JSON; the content checks that the paper's design
    intends (Section 3.5) were applied afterwards by
    scripts/verify_blind_coders_quotations_against_windows.py. The published runs were made
    without the flag --verify-at-run-time, and without the flag the script still behaves
    exactly so: schema check and JSON re-ask only. The content checks are: row and who must
    match the packet header, every id in holds must be one of the position's candidate view
    ids or "OTHER", and the quote must occur in the served window, as written (whitespace
    collapsed) or after the orthographic fold of arabic_text_fold.py (the module beside this
    script, identical to the copy in the JQS folder and to what the verifier applies: vowel
    marks, tatweel, bidirectional controls and punctuation removed, hamza/alif forms, final
    ya and ta marbuta unified, whitespace collapsed), so that a quotation differing only in
    spelling passes; an empty quote fails unless the type is silent (a commentator who
    says nothing has nothing to quote).
    Annotation, always on: every record carries the key "verification", the list of failed
    checks ("row", "who", "holds", "quote"; empty when all pass; ["parse_error"] when no
    answer parsed). Writing this key changes no behaviour of the run; of the published
    records only the 46 of the rescue pass (paper Section 4.2) have it.
    Retry, only with --verify-at-run-time: when a check fails the position is sent once more
    with a short correction naming the failed check(s); if the second answer fails too, it is
    recorded as it is. This is the design of Section 3.5 of the paper (verification at run
    time with one retry) for future runs; the service runners, one packet per call, only flag.

Server errors (added 5 Nov 2026)
    A call that fails with a network error (connection refused or reset, HTTP error, socket
    timeout) is repeated up to CALL_ATTEMPTS times, waiting CALL_RETRY_WAIT_SECONDS times the
    attempt number between tries. When every attempt fails the position is recorded with
    type PARSE_ERROR, verification ["parse_error"] and the error in the note, and the run goes
    on with the next position; the script does not crash. Such a record is not re-coded on a
    resume (its row and who are in the file); delete the line to have the position coded again.
"""

import argparse
import glob
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

# The shared orthographic fold sits beside this script; `python -I` does not put the script folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arabic_text_fold import fold, quotation_occurs  # noqa: E402  (import after the path insert)

BLIND_CODING_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKETS_GLOB = os.path.join(BLIND_CODING_FOLDER, "data", "blind-packet-*.md")
RULE_PATH = os.path.join(BLIND_CODING_FOLDER, "Blind-coding-prompt-for-external-AI-coder-v02.md")
RESULTS_FOLDER = os.path.join(BLIND_CODING_FOLDER, "results")
POSITIONS_FILE_NAME = "positions.jsonl"
MODEL_INFO_FILE_NAME = "model-info.json"

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
EXPECTED_POSITIONS = 134  # packets 26-27: 67 hawwari + 67 himyan

# Context window in tokens, requested for every model alike (paper Section 3.1, Reproducibility):
# the rule plus one window must fit. Jais 13B's native context is 4,096 tokens; the runs
# requested 8,192 nevertheless, and the paper says so (Limitations).
NUM_CTX = 8192

# slug: (Ollama model tag, citation name, context window requested); in download order.
# All in four-bit Q4_K_M quantisation.
MODELS = {
    "allam":    ("hf.co/bartowski/ALLaM-AI_ALLaM-7B-Instruct-preview-GGUF:Q4_K_M", "ALLaM-7B-Instruct-preview (SDAIA/HUMAIN, Saudi Arabia), Q4_K_M", NUM_CTX),
    "fanar":    ("hf.co/mradermacher/Fanar-1-9B-Instruct-GGUF:Q4_K_M", "Fanar-1-9B-Instruct (QCRI/HBKU, Qatar), Q4_K_M", NUM_CTX),
    "llama":    ("llama3.1:8b", "Llama 3.1 8B Instruct (Meta), Q4_K_M", NUM_CTX),
    "qwen":     ("qwen3:14b", "Qwen3-14B (Alibaba), Q4_K_M", NUM_CTX),
    "gemma":    ("gemma3:12b", "Gemma 3 12B (Google), Q4_K_M", NUM_CTX),
    "deepseek": ("deepseek-r1:14b", "DeepSeek-R1-Distill-Qwen-14B (DeepSeek), Q4_K_M", NUM_CTX),
    "acegpt":   ("hf.co/mradermacher/AceGPT-v2-8B-Chat-GGUF:Q4_K_M", "AceGPT-v2-8B-Chat (KAUST / CUHK-Shenzhen), Q4_K_M", NUM_CTX),
    "falcon":   ("hf.co/tiiuae/Falcon-H1-7B-Instruct-GGUF:Q4_K_M", "Falcon-H1-7B-Instruct (TII, UAE), Q4_K_M", NUM_CTX),
    # Native context 4,096 tokens; 8,192 requested all the same (see NUM_CTX).
    "jais":     ("hf.co/RichardErkhov/inceptionai_-_jais-adapted-13b-chat-gguf:Q4_K_M", "Jais-adapted-13B-chat (Inception/G42, UAE), Q4_K_M", NUM_CTX),
}
QUANTISATION = "Q4_K_M"
# Reasoning models: chain-of-thought is switched off (think=false) because otherwise qwen3 and
# deepseek-r1 spend minutes of reasoning per position and overrun the output budget (NUM_PREDICT).
THINKING_MODELS = {"qwen3:14b", "deepseek-r1:14b"}

# Call options, identical for every model (paper Section 3.1, Reproducibility).
TEMPERATURE = 0
NUM_PREDICT = 1200  # output budget in tokens: one short JSON object
CHAT_TIMEOUT_SECONDS = 1800
JSON_ATTEMPTS = 2  # a second call is made when the first answer is not valid JSON
VERIFICATION_ATTEMPTS = 2  # with --verify-at-run-time: a second call is made when the first parsed answer fails a content check
CALL_ATTEMPTS = 5  # how often one HTTP call is tried when the server does not answer (see post_json)
CALL_RETRY_WAIT_SECONDS = 30  # multiplied by the attempt number: 30, 60, 90, 120 s between tries
# Errors that mean the server could not be reached or did not answer in time: the call is repeated.
NETWORK_ERRORS = (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)  # URLError includes HTTPError
ERROR_PAUSE_SECONDS = 10  # pause after an unexpected error before the next position
MODEL_WAIT_CHECKS = 720  # x MODEL_WAIT_SECONDS = up to 12 hours waiting for a model to be pulled
MODEL_WAIT_SECONDS = 60
PROGRESS_EVERY = 25  # positions between progress lines


def read_text(path):
    """Return the whole content of a UTF-8 text file."""
    with open(path, encoding="utf8") as handle:
        return handle.read()


def load_system_prompt():
    """Return the written rule (the part of the prompt file after the first "---" line) adapted to one position per call."""
    rule_text = read_text(RULE_PATH).split("\n---\n", 1)[1].strip()
    return rule_text.replace("The attached file contains a numbered list of positions.", "You will be given ONE position at a time.") + \
        "\n\nKeep `quote` short: one clause or one sentence, never more than 200 characters."


# The system prompt is the written rule, with the packet sentence replaced for one-position calls.
SYSTEM_PROMPT = load_system_prompt()
USER_PROMPT_PREFIX = "Code this one position under the rule. Reply with one JSON object only.\n\n"
RETRY_SUFFIX = "\n\nYour previous answer was not valid JSON. Answer again with one short valid JSON object."
# Correction sent when a parsed answer fails a content check (added 5 Nov 2026); {checks} names the failed check(s).
CORRECTION_SUFFIX = ("\n\nYour previous answer failed these checks: {checks}. Answer again with one JSON object "
                     "whose row and who match the header, whose holds uses only the listed view ids or OTHER, "
                     "and whose quote is copied verbatim from the text.")
CHECK_DESCRIPTIONS = {"row": "row did not match the header", "who": "who did not match the header",
                      "holds": "holds contained an id that is not a candidate view id or OTHER",
                      "quote": "quote does not occur verbatim in the text"}
OTHER_VIEW_ID = "OTHER"
SILENT_TYPE = "silent"  # the one type that may carry no quotation: a commentator who says nothing has nothing to quote
# Output schema passed to Ollama's "format" option, so the answer is machine-readable and holds the five types only.
OUTPUT_SCHEMA = {"type": "object", "properties": {"row": {"type": "integer"}, "who": {"type": "string"},
                 "type": {"type": "string", "enum": ["prefers", "single", "combines", "lists_no_choice", "silent"]},
                 "holds": {"type": "array", "items": {"type": "string"}}, "quote": {"type": "string"}, "note": {"type": "string"}},
                 "required": ["row", "who", "type", "holds", "quote", "note"]}
PARSE_ERROR_TYPE = "PARSE_ERROR"
PARSE_ERROR_NOTE_CHARACTERS = 300  # how much of an unparsable answer is kept in the note
PARSE_ERROR_VERIFICATION = ["parse_error"]  # the verification list of a record no answer could be parsed for
CALL_FAILED_NOTE = "server call failed after {attempts} attempts: {error}"  # note of a record no answer was received for

# One packet entry: header "## row | unit | phrase | who", a "views:" line, a blank line, then the window.
POSITION_HEADER_PATTERN = re.compile(r"## (\d+) \| ([^|]+)\| ([^|]+)\| (\w+)\n(views: [^\n]*)\n\n(.*)", re.S)
# One candidate view in the views line: "V1 = label ; V2 = label ; ..."; the id is the token before " = ".
VIEW_ID_PATTERN = re.compile(r"(?:^views: |; )\s*(\w+) = ")


def load_positions():
    """Return [(row, who, full entry text)] for every position in the packets, in packet and file order."""
    positions = []
    for packet_path in sorted(glob.glob(PACKETS_GLOB)):
        for entry in re.split(r"\n(?=## )", read_text(packet_path)):
            match = POSITION_HEADER_PATTERN.match(entry.strip())
            if match:
                positions.append((int(match.group(1)), match.group(4), entry.strip()))
    return positions


class OllamaCallFailed(Exception):
    """Raised by post_json when every one of CALL_ATTEMPTS tries failed with a network error."""


def post_json(path, body, timeout=CHAT_TIMEOUT_SECONDS):
    """POST a JSON body to the Ollama server and return the decoded JSON answer.

    A network error (NETWORK_ERRORS: connection refused or reset, HTTP error, socket timeout)
    is reported and the call repeated after CALL_RETRY_WAIT_SECONDS times the attempt number,
    up to CALL_ATTEMPTS times in all; then OllamaCallFailed is raised with the last error.
    """
    request = urllib.request.Request(OLLAMA_URL + path, data=json.dumps(body).encode("utf8"),
                                     headers={"Content-Type": "application/json"})
    last_error = None
    for attempt in range(1, CALL_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except NETWORK_ERRORS as error:
            last_error = error
            print(f"  call attempt {attempt} of {CALL_ATTEMPTS} failed: {error}", flush=True)
            if attempt < CALL_ATTEMPTS:
                time.sleep(CALL_RETRY_WAIT_SECONDS * attempt)
    raise OllamaCallFailed(f"{type(last_error).__name__}: {last_error}")


def wait_for_model(model):
    """Block until the model tag is listed by the Ollama server (it is pulled separately); exit after 12 hours."""
    for check in range(MODEL_WAIT_CHECKS):
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags") as response:
            tags = [entry["name"] for entry in json.load(response)["models"]]
        if model in tags:
            return
        if check == 0:
            print("waiting for download of", model, flush=True)
        time.sleep(MODEL_WAIT_SECONDS)
    raise SystemExit("model never appeared: " + model)


def first_json_object_text(content):
    """Return the text of the first complete {...} object in content, or None.

    Braces are counted from the first "{" to its matching "}", skipping braces inside JSON
    strings (and escaped quotes inside them), so that a nested object or a brace in a quote
    does not cut the object short, as a non-greedy regex would.
    """
    start = content.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        character = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return content[start:index + 1]
    return None


def extract_json_object(content):
    """Return (parsed value, True) when the whole answer is JSON; else (first {...} object parsed or None, False)."""
    try:
        return json.loads(content), True
    except Exception:
        object_text = first_json_object_text(content)
        try:
            return (json.loads(object_text) if object_text else None), False
        except Exception:
            return None, False


def ask_until_json(body, user_prompt):
    """Send the position up to JSON_ATTEMPTS times until an answer parses; return (coding or None, last answer text).

    When the first answer is not valid JSON (even with the schema some models return prose),
    the position is sent again with a reminder. The body's user message is left as the last
    message sent.
    """
    body["messages"][1]["content"] = user_prompt
    coding = None
    content = ""
    for _attempt in range(JSON_ATTEMPTS):
        content = post_json("/api/chat", body)["message"]["content"]
        coding, whole_answer_was_json = extract_json_object(content)
        # A whole-answer parse is accepted as it is; a {...} span cut out of prose is accepted only when non-empty.
        if whole_answer_was_json or coding:
            break
        body["messages"][1]["content"] = user_prompt + RETRY_SUFFIX
    return coding, content


def candidate_view_ids(entry_text):
    """Return the set of candidate view ids listed in the entry's "views:" line."""
    views_line = POSITION_HEADER_PATTERN.match(entry_text).group(5)
    return set(VIEW_ID_PATTERN.findall(views_line))


def served_window(entry_text):
    """Return the text window of a packet entry (everything after the blank line that follows the views line)."""
    return POSITION_HEADER_PATTERN.match(entry_text).group(6)


def failed_checks(coding, row, who, view_ids, window):
    """Return the list of content checks the parsed answer fails: "row", "who", "holds", "quote" (empty when all pass).

    row and who must match the packet header; every id in holds must be a candidate view id or
    OTHER; the quote must occur in the window as written (whitespace collapsed) or after the
    orthographic fold of arabic_text_fold.py applied to both (an empty quote passes only when the type is silent).
    """
    failed = []
    if coding.get("row") != row:
        failed.append("row")
    if coding.get("who") != who:
        failed.append("who")
    holds = coding.get("holds", [])
    if not isinstance(holds, list):
        holds = [holds]
    if any(str(held) not in view_ids and str(held) != OTHER_VIEW_ID for held in holds):
        failed.append("holds")
    quote = str(coding.get("quote") or "")
    quote_required = coding.get("type") != SILENT_TYPE  # only a silent position may leave the quote empty
    # Tested on the folded quote: a quote of vowel marks or punctuation only counts as empty, so
    # that it passes on a silent position (as before 7 Nov 2026) and fails on any other.
    folded_quote = fold(quote)
    if (quote_required and not folded_quote) or (folded_quote and not quotation_occurs(quote, window)):
        failed.append("quote")
    return failed


def parse_error_record(note):
    """Return the coding recorded when no answer could be used: type PARSE_ERROR, empty holds and quote, the note given."""
    return {"type": PARSE_ERROR_TYPE, "holds": [], "quote": "", "note": note}


def code_one_position(model, num_ctx, row, who, entry_text, verify_at_run_time):
    """Send one position to the model and return its coding as a dict with row, who, seconds and verification added.

    The call is made twice at most for JSON (see ask_until_json); if both fail the record
    carries type PARSE_ERROR and the start of the answer in the note, and if the server could
    not be reached at all (OllamaCallFailed) the note says so instead. A parsed answer is
    always annotated with its failed content checks (failed_checks). Only with
    verify_at_run_time, on a failure, is the position sent once more with a correction naming
    the failed check(s), and the second answer recorded whatever its checks say.
    """
    user_prompt = USER_PROMPT_PREFIX + entry_text
    body = {"model": model, "stream": False, "format": OUTPUT_SCHEMA,
            "options": {"temperature": TEMPERATURE, "num_ctx": num_ctx, "num_predict": NUM_PREDICT},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]}
    if model in THINKING_MODELS:
        body["think"] = False
    started_at = time.time()
    try:
        coding, content = ask_until_json(body, user_prompt)
        if coding is None:
            coding = parse_error_record(content[:PARSE_ERROR_NOTE_CHARACTERS])
            verification = list(PARSE_ERROR_VERIFICATION)
        else:
            view_ids, window = candidate_view_ids(entry_text), served_window(entry_text)
            verification = failed_checks(coding, row, who, view_ids, window)
            if verify_at_run_time:
                for _attempt in range(1, VERIFICATION_ATTEMPTS):
                    if not verification:
                        break
                    checks = "; ".join(CHECK_DESCRIPTIONS[check] for check in verification)
                    corrected, _content = ask_until_json(body, user_prompt + CORRECTION_SUFFIX.format(checks=checks))
                    if corrected is not None:
                        coding = corrected
                        verification = failed_checks(coding, row, who, view_ids, window)
    except OllamaCallFailed as error:
        # The server never answered: record the position as a parse error with the reason, so the run goes on.
        coding = parse_error_record(CALL_FAILED_NOTE.format(attempts=CALL_ATTEMPTS, error=error))
        verification = list(PARSE_ERROR_VERIFICATION)
    coding["row"], coding["who"] = row, who
    coding.setdefault("holds", [])
    coding.setdefault("quote", "")
    coding.setdefault("note", "")
    if not isinstance(coding["holds"], list):
        coding["holds"] = [str(coding["holds"])]
    coding["seconds"] = round(time.time() - started_at, 1)
    coding["verification"] = verification
    return coding


def load_done_keys(positions_path):
    """Return (set of (row, who) already present in positions.jsonl, number of corrupt lines skipped), so the run can resume.

    A corrupt line (a write cut short by an interruption) is skipped and counted, not fatal:
    its position is simply coded again.
    """
    done = set()
    corrupt_lines = 0
    if os.path.exists(positions_path):
        with open(positions_path, encoding="utf8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    corrupt_lines += 1
                    continue
                done.add((record["row"], record["who"]))
    return done, corrupt_lines


def write_model_info(output_folder, slug, model, citation, num_ctx, position_count):
    """Record the exact model and settings beside the answers, for citation."""
    info = {"slug": slug, "ollama_model": model, "citation": citation, "quantisation": QUANTISATION, "positions": position_count,
            "one_position_per_call": True, "temperature": TEMPERATURE, "num_ctx": num_ctx, "json_schema_output": True}
    with open(os.path.join(output_folder, MODEL_INFO_FILE_NAME), "w", encoding="utf8") as handle:
        json.dump(info, handle, indent=1)


def run_model(slug, positions, limit, reverse, verify_at_run_time):
    """Code every position not yet in results/<slug>/positions.jsonl with one model and write model-info.json.

    verify_at_run_time is passed to code_one_position (retry once on a failed content check).
    """
    model, citation, num_ctx = MODELS[slug]
    wait_for_model(model)
    output_folder = os.path.join(RESULTS_FOLDER, slug)
    os.makedirs(output_folder, exist_ok=True)
    positions_path = os.path.join(output_folder, POSITIONS_FILE_NAME)
    done, corrupt_lines = load_done_keys(positions_path)
    todo = [position for position in positions if (position[0], position[1]) not in done]
    if reverse:
        todo.reverse()
    if limit:
        todo = todo[:max(0, limit - len(done))]
    print(f"{slug}: {model} | {len(done)} done, {len(todo)} to code" + (f", {corrupt_lines} corrupt line(s) skipped" if corrupt_lines else ""), flush=True)
    started_at = time.time()
    with open(positions_path, "a", encoding="utf8") as output_file:
        for index, (row, who, entry_text) in enumerate(todo, 1):
            # Another machine sharing the run may have coded it meanwhile.
            if (row, who) in load_done_keys(positions_path)[0]:
                continue
            try:
                coding = code_one_position(model, num_ctx, row, who, entry_text, verify_at_run_time)
            except Exception as error:
                # An unexpected error (network errors are handled in post_json): report it, pause, and go on;
                # the position stays uncoded for a later resume.
                print("  error", row, who, error, flush=True)
                time.sleep(ERROR_PAUSE_SECONDS)
                continue
            output_file.write(json.dumps(coding, ensure_ascii=False) + "\n")
            output_file.flush()
            if index % PROGRESS_EVERY == 0 or index == len(todo):
                print(f"  {slug} {len(done) + index}/{len(positions)}  {int(time.time() - started_at)} s elapsed", flush=True)
    write_model_info(output_folder, slug, model, citation, num_ctx, len(positions))


def parse_arguments():
    """Parse the model slugs (or "all") and the --limit / --reverse / --verify-at-run-time options."""
    parser = argparse.ArgumentParser(description="Blind-code the 134 Oman positions with open-weight models served by Ollama.")
    parser.add_argument("slugs", nargs="+", metavar="slug",
                        help="model slug(s) from " + ", ".join(MODELS) + ", or 'all'")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many positions in total (test run)")
    parser.add_argument("--reverse", action="store_true", help="code from the last position backwards")
    parser.add_argument("--verify-at-run-time", action="store_true",
                        help="retry a position once when its parsed answer fails a content check "
                             "(the published runs were made without this; default off)")
    arguments = parser.parse_args()
    if arguments.slugs == ["all"]:
        arguments.slugs = list(MODELS)
    unknown = [slug for slug in arguments.slugs if slug not in MODELS]
    if unknown:
        parser.error("unknown slug(s): " + ", ".join(unknown))
    return arguments


def main():
    """Load the packets, check the position count, and run each requested model in turn."""
    arguments = parse_arguments()
    positions = load_positions()
    if len(positions) != EXPECTED_POSITIONS:
        sys.exit(f"expected {EXPECTED_POSITIONS} positions in the packets, found {len(positions)}")
    for slug in arguments.slugs:
        run_model(slug, positions, arguments.limit, arguments.reverse, arguments.verify_at_run_time)
    print("done; compare with: python -I scripts/compare_oman_coders_against_claude_reference.py")


if __name__ == "__main__":
    main()
