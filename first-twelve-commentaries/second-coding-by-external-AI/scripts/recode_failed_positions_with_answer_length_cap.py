"""Re-code failed positions with a length cap on the answer's quote and note (rescue pass, 7 Nov 2026).

Why
    Some local models never close their JSON answer: Jais repeats itself in
    `note`, AceGPT, ALLaM and Falcon copy an ever longer `quote`, until the
    output budget (NUM_PREDICT) runs out and the reply cannot be parsed. At
    temperature 0 a plain re-run mostly fails the same way: on 7 Nov 2026 it
    recovered 12 of the 46 positions, and the other 34 are coded by this script.
    It is not strictly repeatable: four of those 34 had been answered without the
    cap in the discarded attempt of 5 Nov 2026 (README, rescue pass), with the
    same type. One position (Jais, row 64, ibnJuzayy) failed otherwise: the
    server answered HTTP 500 on every call without the cap, and with the cap
    the model answered. A maxLength on `quote` and `note` in the JSON schema that
    Ollama enforces makes the answer close. In a test of 7 Nov 2026 on six
    failed positions every reply parsed, and the five whose cut-off reply
    could be read kept the same type and holds.

What it does
    Loads one of the two Ollama runners unchanged
        first-twelve-commentaries/second-coding-by-external-AI/scripts/run_blind_coding_through_local_ollama_models.py
        paper-and-two-added-commentaries/blind-coding/scripts/run_blind_coding_through_local_ollama_models.py
    adds the maxLength caps to its answer schema, marks every record it codes
    with "answer_length_cap": ANSWER_LENGTH_CAP, adds the key
    "answer_length_cap_on_rescued_positions" to model-info.json, and then runs the runner's own main() for the slugs given.
    Every other setting (prompt, temperature, context, output budget, retries)
    is the runner's own. The runner skips positions already recorded, so only
    positions whose PARSE_ERROR records were first removed with
    remove_parse_error_records_for_recoding.py are coded.

Reads / writes
    Whatever the chosen runner reads and writes: results/<slug>/positions.jsonl
    (appended) and results/<slug>/model-info.json, in the runner's job folder.
    The Ollama server comes from the environment variable OLLAMA_URL.

Run
    python -I scripts/recode_failed_positions_with_answer_length_cap.py <runner path> <slug> [<slug> ...]
"""

import copy
import importlib.util
import json
import os
import sys

ANSWER_LENGTH_CAP = 200  # characters; the prompt already asks for a quote of at most 200 characters
CAPPED_FIELDS = ("quote", "note")
SCHEMA_NAMES = ("ANSWER_SCHEMA", "OUTPUT_SCHEMA")  # the first-set runner's name, the Oman runner's name
CAP_KEY = "answer_length_cap"
MODEL_INFO_FILE_NAME = "model-info.json"
MINIMUM_ARGUMENT_COUNT = 3  # the script name, the runner path and at least one slug


def load_runner(runner_path):
    """Load a runner file as a module without starting it (its main() is guarded)."""
    specification = importlib.util.spec_from_file_location("ollama_runner", runner_path)
    runner = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(runner)
    return runner


def cap_schema(runner):
    """Replace the runner's answer schema by a copy with maxLength on quote and note."""
    for name in SCHEMA_NAMES:
        if hasattr(runner, name):
            schema = copy.deepcopy(getattr(runner, name))
            for field in CAPPED_FIELDS:
                schema["properties"][field]["maxLength"] = ANSWER_LENGTH_CAP
            setattr(runner, name, schema)
            return
    raise SystemExit("runner has no answer schema named " + " or ".join(SCHEMA_NAMES))


def mark_records(runner):
    """Wrap code_one_position so that every record says it was coded with the cap."""
    code_one_position = runner.code_one_position

    def capped_code_one_position(*arguments, **keywords):
        """Code the position as the runner does and add the cap key to the record."""
        record = code_one_position(*arguments, **keywords)
        record[CAP_KEY] = ANSWER_LENGTH_CAP
        return record

    runner.code_one_position = capped_code_one_position


def mark_model_info(runner):
    """Wrap write_model_info so that model-info.json records the rescue pass's cap."""
    write_model_info = runner.write_model_info

    def capped_write_model_info(output_folder, *arguments):
        """Write model-info.json as the runner does, then add the cap key."""
        write_model_info(output_folder, *arguments)
        info_path = os.path.join(output_folder, MODEL_INFO_FILE_NAME)
        with open(info_path, encoding="utf8") as handle:
            info = json.load(handle)
        info[CAP_KEY + "_on_rescued_positions"] = ANSWER_LENGTH_CAP
        with open(info_path, "w", encoding="utf8") as handle:
            json.dump(info, handle, indent=1)

    runner.write_model_info = capped_write_model_info


def main():
    """Load the runner, apply the cap and the markers, and run it for the slugs given."""
    if len(sys.argv) < MINIMUM_ARGUMENT_COUNT:
        raise SystemExit(__doc__)
    runner_path, slugs = os.path.abspath(sys.argv[1]), sys.argv[2:]
    runner = load_runner(runner_path)
    cap_schema(runner)
    mark_records(runner)
    mark_model_info(runner)
    sys.argv = [runner_path] + slugs  # the runner parses its own arguments
    runner.main()


if __name__ == "__main__":
    main()
