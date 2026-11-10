"""Code the 624 positions with open-weight models served by Ollama, one position per call.

Purpose
    This is how the nine local models (ALLaM, Fanar, Llama 3.1, Qwen3,
    Gemma 3, DeepSeek-R1, AceGPT-v2, Falcon-H1, Jais) coded the 624
    positions between 2 and 4 November 2026. Each position (header, candidate
    views and text window, cut from the 25 packets in data/) is sent on its
    own to the Ollama chat endpoint with the blind coding prompt as system
    message, temperature 0, an 8,192-token context, and the answer forced
    into a JSON schema; the answer line is appended to the model's
    positions.jsonl in the same format as the other coders.

Reads
    Blind-coding-prompt-for-external-AI-coder-v01.md (the part after the
        first "---" line), adapted for one position per call: see SYSTEM_PROMPT.
    data/blind-packet-*.md: the 624 positions.
    Ollama server: the environment variable OLLAMA_URL, default
        http://localhost:11434 (a server on this PC). The runs of 2 to
        4 November 2026 used servers on other office PCs as well, for example
        OLLAMA_URL=http://ollama-server.example:11434 (a placeholder name; put the
        server's own address).
        The models are pulled separately (ollama pull <name> for each name in MODELS);
        the runner waits until a model appears in the server's tag list.
    No key or secret is involved.

Writes
    results/<slug>/positions.jsonl: one JSON line per position
        {row, who, type, holds, quote, note, seconds, verification}; an
        answer that is not valid JSON after one re-ask is written with type
        PARSE_ERROR and the first 300 characters of the reply in note, and
        later counts as a disagreement in every measure.
    results/<slug>/model-info.json: the exact Ollama model name, the citation
        name and the settings, written when the model's run ends.

Run (from the second-coding-by-external-AI folder)
    python -I scripts/run_blind_coding_through_local_ollama_models.py <slug> [<slug> ...]
    python -I scripts/run_blind_coding_through_local_ollama_models.py all
    Options: --limit N   code only the first N positions (test run)
             --reverse   code from the last position backwards
             --middle    start halfway through the list
             --verify-at-run-time
                         retry a position once when its parsed answer fails
                         a content check (see below); off by default
    Slugs: the keys of MODELS below. Positions already in positions.jsonl are
    skipped, and the file is re-read before every call, so several machines
    can share one model's run on one file (one forward, one --reverse, one
    --middle) and any run resumes after a stop.
    Then: python -I scripts/merge_external_ai_results_and_compare.py results/<slug> <panel-majority.json>

Content verification (added 5 Nov 2026, after the runs reported in the papers)
    The runs of 2 to 4 November 2026 enforced the JSON schema only, with one
    re-ask when an answer was not valid JSON; the content checks the design
    intends (SNM05 paper, Section 3.5) were applied afterwards
    (paper-and-two-added-commentaries/scripts/verify_blind_coders_quotations_against_windows.py).
    The published runs were made without the flag --verify-at-run-time, and
    without the flag the script still behaves exactly so: schema check and
    JSON re-ask only. The content checks are: row and who must match the
    packet header, every id in holds must be one of the position's candidate
    view ids or "OTHER", and the quote must occur in the served window, as
    written (whitespace collapsed) or after the orthographic fold of
    arabic_text_fold.py (the module beside this script, identical to the
    copy in the Oman blind-coding folder and to what the verifier applies:
    vowel marks, tatweel, bidirectional controls and punctuation removed,
    hamza/alif forms, final ya and ta marbuta unified, whitespace collapsed),
    so that a quotation differing only in spelling passes; an empty quote fails
    unless the type is silent (a commentator who says nothing has nothing to quote).
    Annotation, always on: every record carries the key "verification", the
    list of failed checks ("row", "who", "holds", "quote"; empty when all
    pass; ["parse_error"] when no answer parsed). Writing this key changes
    no behaviour of the run; of the published records only the 46 of the
    rescue pass (paper Section 4.2) have it.
    Retry, only with --verify-at-run-time: when a check fails the position is
    sent once more with a short correction naming the failed check(s); if the
    second answer fails too, it is recorded as it is. This is the design of
    Section 3.5 of the SNM05 paper (verification at run time with one retry)
    for future runs; the service runners, one packet per call, only flag.

Server errors (added 5 Nov 2026)
    A call that fails with a network error (connection refused or reset,
    HTTP error, socket timeout) is repeated up to CALL_ATTEMPTS times,
    waiting CALL_RETRY_WAIT_SECONDS times the attempt number between tries.
    When every attempt fails the position is recorded with type PARSE_ERROR,
    verification ["parse_error"] and the error in the note, and the run goes
    on with the next position; the script does not crash. Such a record is
    not re-coded on a resume (its row and who are in the file); delete the
    line to have the position coded again.

Feeds
    results/<slug>/positions.jsonl for the nine local models, hence the
    agreement table in results/Nine-local-models-results-and-agreement-2026-11-04.md
    and the local-model figures in the JQS article and the SNM05 paper.
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

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_FILE = os.path.join(PROJECT_FOLDER, "Blind-coding-prompt-for-external-AI-coder-v01.md")
PACKETS_GLOB = os.path.join(PROJECT_FOLDER, "data", "blind-packet-*.md")
RESULTS_ROOT = os.path.join(PROJECT_FOLDER, "results")
POSITIONS_FILE_NAME = "positions.jsonl"
MODEL_INFO_FILE_NAME = "model-info.json"

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)

# Context window in tokens, requested for every model alike: the system
# prompt plus a 3,000-character Arabic window must fit. Jais 13B's native
# context is 4,096 tokens; the runs requested 8,192 nevertheless, and the
# SNM05 paper says so (Limitations).
NUM_CTX = 8192

# slug: (Ollama model name, citation name, context window requested); in download order.
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
# Reasoning models: chain-of-thought switched off (think=false), answer only.
# With it on, qwen3 / deepseek-r1 spend minutes of chain-of-thought per
# position and overrun NUM_PREDICT.
THINKING_MODELS = {"qwen3:14b", "deepseek-r1:14b"}
QUANTISATION = "Q4_K_M"

# Generation settings, identical for all nine models.
TEMPERATURE = 0
NUM_PREDICT = 1200  # output tokens: one JSON object with a short quote

EXPECTED_POSITIONS = 624
CALL_TIMEOUT_SECONDS = 1800
JSON_ATTEMPTS = 2  # the position is asked once more if the first answer is not valid JSON
VERIFICATION_ATTEMPTS = 2  # with --verify-at-run-time: the position is asked once more if the first parsed answer fails a content check
CALL_ATTEMPTS = 5  # how often one HTTP call is tried when the server does not answer (see post_json)
CALL_RETRY_WAIT_SECONDS = 30  # multiplied by the attempt number: 30, 60, 90, 120 s between tries
# Errors that mean the server could not be reached or did not answer in time: the call is repeated.
NETWORK_ERRORS = (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)  # URLError includes HTTPError
PARSE_ERROR_TYPE = "PARSE_ERROR"
PARSE_ERROR_NOTE_CHARACTERS = 300
PARSE_ERROR_VERIFICATION = ["parse_error"]  # the verification list of a record no answer could be parsed for
CALL_FAILED_NOTE = "server call failed after {attempts} attempts: {error}"  # note of a record no answer was received for
ERROR_WAIT_SECONDS = 10  # pause after an unexpected error (network errors are handled in post_json) before the next position
MODEL_WAIT_MINUTES = 720  # up to 12 hours for a model download to finish, polled once a minute
MODEL_POLL_SECONDS = 60
PROGRESS_EVERY = 25  # positions between progress lines

# The JSON schema Ollama's structured output enforces on every answer.
ANSWER_SCHEMA = {"type": "object", "properties": {"row": {"type": "integer"}, "who": {"type": "string"},
          "type": {"type": "string", "enum": ["prefers", "single", "combines", "lists_no_choice", "silent"]},
          "holds": {"type": "array", "items": {"type": "string"}}, "quote": {"type": "string"}, "note": {"type": "string"}},
          "required": ["row", "who", "type", "holds", "quote", "note"]}

# The packet prompt speaks of an attached file of positions; here each call
# carries one position, and the quote is capped so that it fits NUM_PREDICT.
PACKET_SENTENCE = "The attached file contains a numbered list of positions."
ONE_POSITION_SENTENCE = "You will be given ONE position at a time."
QUOTE_LENGTH_RULE = "\n\nKeep `quote` short: one clause or one sentence, never more than 200 characters."
USER_MESSAGE_PREFIX = "Code this one position under the rule. Reply with one JSON object only.\n\n"
REASK_SUFFIX = "\n\nYour previous answer was not valid JSON. Answer again with one short valid JSON object."
# Correction sent when a parsed answer fails a content check (added 5 Nov
# 2026); {checks} names the failed check(s).
CORRECTION_SUFFIX = ("\n\nYour previous answer failed these checks: {checks}. Answer again with one JSON object "
                     "whose row and who match the header, whose holds uses only the listed view ids or OTHER, "
                     "and whose quote is copied verbatim from the text.")
CHECK_DESCRIPTIONS = {"row": "row did not match the header", "who": "who did not match the header",
                      "holds": "holds contained an id that is not a candidate view id or OTHER",
                      "quote": "quote does not occur verbatim in the text"}
OTHER_VIEW_ID = "OTHER"
SILENT_TYPE = "silent"  # the one type that may carry no quotation: a commentator who says nothing has nothing to quote

# One position block in a packet: header "## row | sura | phrase | who", a
# "views:" line, a blank line, then the text window.
POSITION_BLOCK = re.compile(r"## (\d+) \| ([^|]+)\| ([^|]+)\| (\w+)\n(views: [^\n]*)\n\n(.*)", re.S)
# One candidate view in the views line: "V1 = label ; V2 = label ; ..."; the
# id is the token before " = ".
VIEW_ID_PATTERN = re.compile(r"(?:^views: |; )\s*(\w+) = ")


def read_text(path):
    """Return the whole content of a UTF-8 text file."""
    with open(path, encoding="utf8") as handle:
        return handle.read()


def load_system_prompt():
    """Return the blind coding prompt (the part of the prompt file after the
    first "---" line) adapted to one position per call."""
    prompt = read_text(PROMPT_FILE).split("\n---\n", 1)[1].strip()
    return prompt.replace(PACKET_SENTENCE, ONE_POSITION_SENTENCE) + QUOTE_LENGTH_RULE


SYSTEM_PROMPT = load_system_prompt()


def load_positions():
    """Cut the 624 positions out of the packets in data/.
    Returns a list of (row, who, position text) in packet order."""
    positions = []
    for packet_path in sorted(glob.glob(PACKETS_GLOB)):
        for block in re.split(r"\n(?=## )", read_text(packet_path)):
            match = POSITION_BLOCK.match(block.strip())
            if match:
                positions.append((int(match.group(1)), match.group(4), block.strip()))
    return positions


class OllamaCallFailed(Exception):
    """Raised by post_json when every one of CALL_ATTEMPTS tries failed with a network error."""


def post_json(path, body, timeout=CALL_TIMEOUT_SECONDS):
    """POST a JSON body to the Ollama server and return the parsed reply.

    A network error (NETWORK_ERRORS: connection refused or reset, HTTP error,
    socket timeout) is reported and the call repeated after
    CALL_RETRY_WAIT_SECONDS times the attempt number, up to CALL_ATTEMPTS
    times in all; then OllamaCallFailed is raised with the last error."""
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


def wait_for_model(model_name):
    """Block until the model is in the server's tag list (it is pulled by a
    separate download run); give up after MODEL_WAIT_MINUTES."""
    for minute in range(MODEL_WAIT_MINUTES):
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags") as response:
            available = [model["name"] for model in json.load(response)["models"]]
        if model_name in available:
            return
        if minute == 0:
            print("waiting for download of", model_name, flush=True)
        time.sleep(MODEL_POLL_SECONDS)
    raise SystemExit("model never appeared: " + model_name)


def first_json_object_text(content):
    """Return the text of the first complete {...} object in content, or None.

    Braces are counted from the first "{" to its matching "}", skipping
    braces inside JSON strings (and escaped quotes inside them), so that a
    nested object or a brace in a quote does not cut the object short, as a
    non-greedy regex would."""
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


def embedded_json_object(content):
    """When the whole reply is not valid JSON, try the first complete {...}
    object inside it (some models add words around the object). Returns the
    object, or None."""
    object_text = first_json_object_text(content)
    try:
        return json.loads(object_text) if object_text else None
    except Exception:
        return None


def ask_until_json(body, user_message):
    """Send the position up to JSON_ATTEMPTS times until an answer parses;
    return (answer or None, last reply text).

    The schema makes Ollama constrain the output, but a model can still
    produce an unparsable reply; it is then asked once more with a note that
    the previous answer was not valid JSON."""
    body["messages"][1]["content"] = user_message
    answer = None
    content = ""
    for attempt in range(JSON_ATTEMPTS):
        content = post_json("/api/chat", body)["message"]["content"]
        try:
            answer = json.loads(content)
            break
        except Exception:
            answer = embedded_json_object(content)
            if answer:
                break
            body["messages"][1]["content"] = user_message + REASK_SUFFIX
    return answer, content


def candidate_view_ids(position_text):
    """The set of candidate view ids listed in the block's "views:" line."""
    views_line = POSITION_BLOCK.match(position_text).group(5)
    return set(VIEW_ID_PATTERN.findall(views_line))


def served_window(position_text):
    """The text window of a position block (everything after the blank line
    that follows the views line)."""
    return POSITION_BLOCK.match(position_text).group(6)


def failed_checks(answer, row, who, view_ids, window):
    """The list of content checks a parsed answer fails: "row", "who",
    "holds", "quote" (empty when all pass).

    row and who must match the packet header; every id in holds must be a
    candidate view id or OTHER; the quote must occur in the window as
    written (whitespace collapsed) or after the orthographic fold of
    arabic_text_fold.py applied to both (an empty quote passes only when the type is silent)."""
    failed = []
    if answer.get("row") != row:
        failed.append("row")
    if answer.get("who") != who:
        failed.append("who")
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


def parse_error_record(note):
    """The answer recorded when none could be used: type PARSE_ERROR, empty
    holds and quote, the note given."""
    return {"type": PARSE_ERROR_TYPE, "holds": [], "quote": "", "note": note}


def code_one_position(model_name, num_ctx, row, who, position_text, verify_at_run_time):
    """Send one position to the model and return its answer as a dict.

    The answer is asked for up to twice for JSON (ask_until_json); a second
    failure becomes a PARSE_ERROR record, and so does a server that never
    answered (OllamaCallFailed), with the error in the note. A parsed answer
    is always annotated with its failed content checks (failed_checks). Only
    with verify_at_run_time, on a failure, is the position sent once more
    with a correction naming the failed check(s), and the second answer
    recorded whatever its checks say. row and who are always set from the
    packet header (not trusted from the model), missing keys are filled,
    holds is forced to a list, the call's duration is recorded in seconds,
    and the failed checks in verification.
    """
    user_message = USER_MESSAGE_PREFIX + position_text
    body = {"model": model_name, "stream": False, "format": ANSWER_SCHEMA,
            "options": {"temperature": TEMPERATURE, "num_ctx": num_ctx, "num_predict": NUM_PREDICT},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message}]}
    if model_name in THINKING_MODELS:
        body["think"] = False
    started = time.time()
    try:
        answer, content = ask_until_json(body, user_message)
        if answer is None:
            answer = parse_error_record(content[:PARSE_ERROR_NOTE_CHARACTERS])
            verification = list(PARSE_ERROR_VERIFICATION)
        else:
            view_ids, window = candidate_view_ids(position_text), served_window(position_text)
            verification = failed_checks(answer, row, who, view_ids, window)
            if verify_at_run_time:
                for attempt in range(1, VERIFICATION_ATTEMPTS):
                    if not verification:
                        break
                    checks = "; ".join(CHECK_DESCRIPTIONS[check] for check in verification)
                    corrected, _content = ask_until_json(body, user_message + CORRECTION_SUFFIX.format(checks=checks))
                    if corrected is not None:
                        answer = corrected
                        verification = failed_checks(answer, row, who, view_ids, window)
    except OllamaCallFailed as error:
        # The server never answered: record the position as a parse error with the reason, so the run goes on.
        answer = parse_error_record(CALL_FAILED_NOTE.format(attempts=CALL_ATTEMPTS, error=error))
        verification = list(PARSE_ERROR_VERIFICATION)
    answer["row"], answer["who"] = row, who
    answer.setdefault("holds", [])
    answer.setdefault("quote", "")
    answer.setdefault("note", "")
    if not isinstance(answer["holds"], list):
        answer["holds"] = [str(answer["holds"])]
    answer["seconds"] = round(time.time() - started, 1)
    answer["verification"] = verification
    return answer


def coded_positions(positions_file):
    """The set of (row, who) already in the model's positions.jsonl, and the
    number of corrupt lines skipped (a write cut short by an interruption is
    skipped and counted, and its position is coded again).
    Called before every position: other machines may append to the same file."""
    coded = set()
    corrupt_lines = 0
    if os.path.exists(positions_file):
        with open(positions_file, encoding="utf8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    corrupt_lines += 1
                    continue
                coded.add((record["row"], record["who"]))
    return coded, corrupt_lines


def order_to_code(positions, already_coded, reverse, middle, limit):
    """The positions still to code, in the order this machine takes them:
    forward by default, backwards with --reverse, from the midpoint with
    --middle; cut to --limit positions in total (counting those already done)."""
    todo = [position for position in positions if (position[0], position[1]) not in already_coded]
    if reverse:
        todo.reverse()
    if middle:
        todo = todo[len(todo) // 2:] + todo[:len(todo) // 2]
    if limit:
        todo = todo[:max(0, limit - len(already_coded))]
    return todo


def write_model_info(results_folder, slug, model_name, citation, num_ctx, position_count):
    """Record the exact model and settings beside the answers, for citation."""
    info = {"slug": slug, "ollama_model": model_name, "citation": citation, "quantisation": QUANTISATION,
            "positions": position_count, "one_position_per_call": True, "temperature": TEMPERATURE,
            "num_ctx": num_ctx, "json_schema_output": True}
    with open(os.path.join(results_folder, MODEL_INFO_FILE_NAME), "w", encoding="utf8") as handle:
        json.dump(info, handle, indent=1)


def run_model(slug, positions, reverse, middle, limit, verify_at_run_time):
    """Code every position not yet in results/<slug>/positions.jsonl with one
    model, appending each answer as soon as it arrives; then write model-info.json.
    verify_at_run_time is passed to code_one_position (retry once on a failed content check)."""
    model_name, citation, num_ctx = MODELS[slug]
    wait_for_model(model_name)
    results_folder = os.path.join(RESULTS_ROOT, slug)
    os.makedirs(results_folder, exist_ok=True)
    positions_file = os.path.join(results_folder, POSITIONS_FILE_NAME)
    already_coded, corrupt_lines = coded_positions(positions_file)
    todo = order_to_code(positions, already_coded, reverse, middle, limit)
    print(f"{slug}: {model_name} | {len(already_coded)} done, {len(todo)} to code"
          + (f", {corrupt_lines} corrupt line(s) skipped" if corrupt_lines else ""), flush=True)
    started = time.time()
    with open(positions_file, "a", encoding="utf8") as output:
        for index, (row, who, position_text) in enumerate(todo, 1):
            # Another machine sharing the run may have coded it meanwhile.
            if (row, who) in coded_positions(positions_file)[0]:
                continue
            try:
                answer = code_one_position(model_name, num_ctx, row, who, position_text, verify_at_run_time)
            except Exception as error:
                # An unexpected error (network errors are handled in post_json): report it, pause, go on;
                # the position stays uncoded for a later resume.
                print("  error", row, who, error, flush=True)
                time.sleep(ERROR_WAIT_SECONDS)
                continue
            output.write(json.dumps(answer, ensure_ascii=False) + "\n")
            output.flush()
            if index % PROGRESS_EVERY == 0 or index == len(todo):
                print(f"  {slug} {len(already_coded) + index}/{len(positions)}  {int(time.time() - started)} s elapsed", flush=True)
    write_model_info(results_folder, slug, model_name, citation, num_ctx, len(positions))


def parse_arguments():
    """Parse the slugs (or "all") and the --limit, --reverse, --middle and --verify-at-run-time options."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slugs", nargs="+", help="model slugs (" + ", ".join(MODELS) + ") or 'all'")
    parser.add_argument("--limit", type=int, default=None, help="code only the first N positions (test run)")
    parser.add_argument("--reverse", action="store_true", help="code from the last position backwards (second machine)")
    parser.add_argument("--middle", action="store_true", help="start halfway through the list (third machine)")
    parser.add_argument("--verify-at-run-time", action="store_true",
                        help="retry a position once when its parsed answer fails a content check "
                             "(the published runs were made without this; default off)")
    return parser.parse_args()


def main():
    """Run the chosen models one after the other over the 624 positions."""
    arguments = parse_arguments()
    slugs = list(MODELS) if arguments.slugs == ["all"] else arguments.slugs
    positions = load_positions()
    if len(positions) != EXPECTED_POSITIONS:
        raise SystemExit(f"expected {EXPECTED_POSITIONS} positions, read {len(positions)}")
    for slug in slugs:
        run_model(slug, positions, arguments.reverse, arguments.middle, arguments.limit, arguments.verify_at_run_time)
    print("done; compare each with: python -I scripts/merge_external_ai_results_and_compare.py results/<slug> <panel-majority.json>")


if __name__ == "__main__":
    main()
