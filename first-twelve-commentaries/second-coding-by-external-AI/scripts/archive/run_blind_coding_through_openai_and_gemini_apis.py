"""Run the 24 blind coding packets through the OpenAI and Gemini APIs, one packet per call.

Superseded by run_blind_coding_through_gemini_cli.py; kept for the record of the first attempt.
Moved into scripts/archive/ on 5 Nov 2026; the paths below are resolved from the project folder
(second-coding-by-external-AI), three levels above this file, so the script still runs from there.

Purpose
    Sends each of packets 01 to 24 of 24 in data/ to the OpenAI chat
    completions endpoint (model gpt-5) and to the Gemini generateContent
    endpoint (model gemini-2.5-pro), with the blind coding prompt as system
    instruction, and saves each JSON Lines answer. Written as the API route
    for a GPT and a Gemini second coding; Gemini's accepted coding was in the
    end produced through Gemini CLI (run_blind_coding_through_gemini_cli.py),
    and packet 25 is not covered by this script.

Reads
    Blind-coding-prompt-for-external-AI-coder-v01.md (the part after the
        first "---" line: the prompt the coder receives)
    data/blind-packet-NN-of-24.md (packets 01 to 24)
    API keys: the environment variables OPENAI_API_KEY and GEMINI_API_KEY if
        set, otherwise the first line of OpenAI-API-Key.txt and
        Gemini-API-Key.txt in the _secrets folder of the Claude working
        folder, two levels above this project folder (../../_secrets from
        second-coding-by-external-AI). A key is read only when its API is
        called, and is never printed.

Writes
    results/archive-api-runs/gpt/blind-packet-NN-of-24.jsonl and
    results/archive-api-runs/gemini/blind-packet-NN-of-24.jsonl:
        the answer lines, one JSON object per position. The number of lines
        is printed against the packet's position count (26 expected); a short
        answer is saved as it is and the script does not retry it. A packet
        whose .jsonl already has 26 or more lines is skipped, so the script
        resumes after a stop.

Run (from the second-coding-by-external-AI folder)
    python -I scripts/archive/run_blind_coding_through_openai_and_gemini_apis.py [openai|gemini|both]
    (default both). Then run merge_external_ai_results_and_compare.py on
    results/archive-api-runs/gpt and results/archive-api-runs/gemini.

Feeds
    results/archive-api-runs/<coder>/*.jsonl, compared by merge_external_ai_results_and_compare.py.
"""

import argparse
import glob
import json
import os
import re
import time
import urllib.request

# scripts/archive/<this file> -> scripts -> the project folder.
PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRETS_FOLDER = os.path.join(os.path.dirname(os.path.dirname(PROJECT_FOLDER)), "_secrets")
PROMPT_FILE = os.path.join(PROJECT_FOLDER, "Blind-coding-prompt-for-external-AI-coder-v01.md")
PACKETS_GLOB = os.path.join(PROJECT_FOLDER, "data", "blind-packet-*-of-24.md")
RESULTS_ROOT = os.path.join(PROJECT_FOLDER, "results", "archive-api-runs")  # never the folders of the published coders

OPENAI_MODEL = "gpt-5"
GEMINI_MODEL = "gemini-2.5-pro"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENAI_KEY_FILE = "OpenAI-API-Key.txt"
GEMINI_KEY_FILE = "Gemini-API-Key.txt"
OPENAI_KEY_ENVIRONMENT_VARIABLE = "OPENAI_API_KEY"
GEMINI_KEY_ENVIRONMENT_VARIABLE = "GEMINI_API_KEY"

GEMINI_TEMPERATURE = 0
GEMINI_MAX_OUTPUT_TOKENS = 65536
REQUEST_TIMEOUT_SECONDS = 900
REQUEST_RETRIES = 4  # network or server errors: wait 20, 40, 60, 80 s between tries
RETRY_WAIT_SECONDS = 20
POSITIONS_PER_PACKET = 26  # a saved answer with this many lines counts as done

# Which coders run for each command-line choice; the results subfolder is the
# coder's short name.
CODERS_FOR_CHOICE = {"openai": ("gpt",), "gemini": ("gemini",), "both": ("gpt", "gemini")}
DEFAULT_CHOICE = "both"

# One position header in a packet: "## <row> | ..."
POSITION_HEADER = re.compile(r"^## \d+ \|", re.M)


def read_text(path):
    """Return the whole content of a UTF-8 text file."""
    with open(path, encoding="utf8") as handle:
        return handle.read()


def load_prompt():
    """Return the coder's prompt: the part of the prompt file after the first
    "---" line (the text above it is the instruction to the human operator)."""
    return read_text(PROMPT_FILE).split("\n---\n", 1)[1].strip()


def load_api_key(environment_variable, secrets_file_name):
    """Return an API key from the environment variable, else from the first
    line of the named file in the secrets folder."""
    key = os.environ.get(environment_variable)
    if key:
        return key.strip()
    with open(os.path.join(SECRETS_FOLDER, secrets_file_name), encoding="utf8") as handle:
        return handle.readline().strip()


def post_json(url, headers, body):
    """POST a JSON body and return the parsed JSON reply.

    Retries REQUEST_RETRIES times with a growing wait on any error (timeout,
    HTTP 5xx, rate limit); only the error text is printed, never a key.
    Stops the script after the last failed try.
    """
    for try_number in range(REQUEST_RETRIES):
        try:
            request = urllib.request.Request(
                url, data=json.dumps(body).encode("utf8"),
                headers={"Content-Type": "application/json", **headers})
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.load(response)
        except Exception as error:
            print("  retry", try_number + 1, error)
            time.sleep(RETRY_WAIT_SECONDS * (try_number + 1))
    raise SystemExit("gave up")


def ask_openai(prompt, packet):
    """Code one packet with the OpenAI model; returns the answer text."""
    reply = post_json(
        OPENAI_URL,
        {"Authorization": "Bearer " + load_api_key(OPENAI_KEY_ENVIRONMENT_VARIABLE, OPENAI_KEY_FILE)},
        {"model": OPENAI_MODEL,
         "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": packet}]})
    return reply["choices"][0]["message"]["content"]


def ask_gemini(prompt, packet):
    """Code one packet with the Gemini model; returns the answer text joined
    from the reply's parts."""
    reply = post_json(
        GEMINI_URL,
        {"x-goog-api-key": load_api_key(GEMINI_KEY_ENVIRONMENT_VARIABLE, GEMINI_KEY_FILE)},
        {"system_instruction": {"parts": [{"text": prompt}]},
         "contents": [{"role": "user", "parts": [{"text": packet}]}],
         "generationConfig": {"temperature": GEMINI_TEMPERATURE, "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS}})
    return "".join(part.get("text", "") for part in reply["candidates"][0]["content"]["parts"])


ASK_FUNCTION_FOR_CODER = {"gpt": ask_openai, "gemini": ask_gemini}


def answer_lines(text):
    """The JSON object lines of an answer (lines starting with "{"), kept as
    they are; prose or code fences around them are dropped."""
    return [line for line in text.splitlines() if line.strip().startswith("{")]


def code_packets_with(coder_name, prompt):
    """Run every packet 01 to 24 through one coder, skipping packets whose
    saved answer already has POSITIONS_PER_PACKET lines."""
    ask = ASK_FUNCTION_FOR_CODER[coder_name]
    results_folder = os.path.join(RESULTS_ROOT, coder_name)
    os.makedirs(results_folder, exist_ok=True)
    for packet_path in sorted(glob.glob(PACKETS_GLOB)):
        target_path = os.path.join(results_folder, os.path.basename(packet_path).replace(".md", ".jsonl"))
        if os.path.exists(target_path) and len(answer_lines(read_text(target_path))) >= POSITIONS_PER_PACKET:
            continue
        packet = read_text(packet_path)
        expected_positions = len(POSITION_HEADER.findall(packet))
        print(coder_name, os.path.basename(packet_path), "...", flush=True)
        lines = answer_lines(ask(prompt, packet))
        with open(target_path, "w", encoding="utf8") as handle:
            handle.write("\n".join(lines) + "\n")
        print("  ", len(lines), "of", expected_positions, "positions")


def parse_arguments():
    """Parse the optional choice of API: openai, gemini or both."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("which", nargs="?", default=DEFAULT_CHOICE, choices=sorted(CODERS_FOR_CHOICE),
                        help=f"which API to run (default {DEFAULT_CHOICE})")
    return parser.parse_args()


def main():
    """Run the chosen coders over the 24 packets."""
    arguments = parse_arguments()
    prompt = load_prompt()
    for coder_name in CODERS_FOR_CHOICE[arguments.which]:
        code_packets_with(coder_name, prompt)
    print("done; now run merge_external_ai_results_and_compare.py on results/archive-api-runs/gpt and results/archive-api-runs/gemini")


if __name__ == "__main__":
    main()
