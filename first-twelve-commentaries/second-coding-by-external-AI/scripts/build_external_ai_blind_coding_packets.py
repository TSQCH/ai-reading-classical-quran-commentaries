"""Build blind coding packets 1 to 24 (609 positions) for an external AI coder.

Purpose
    The 23 October 2026 blind packets written for Claude's second coding
    (stage1-output/independent-coding/blind-packet-1.md to -6.md, cut by
    reference-coding/twelve-commentaries/scripts/build_blind_coding_packet.js) hold
    609 positions: the seven core commentators on the 67 disputed phrases (469) and
    the five extended commentators on the 28 phrases then read for them (140) (row,
    sura and verses, phrase, commentator, candidate views, and a window of the
    commentator's own text: 1,500 characters on each side of the first occurrence of
    the opening of the quotation recorded by the reference coding). The comparison
    with that second coding found 15
    windows anchored in the wrong sura. This script rebuilds the packets for an
    external AI coder (Gemini, GPT, ...) with those 15 windows replaced (the 14 of
    al-Tabari by his verified passage on the phrase, row 9 of Ibn Atiyya by a window
    cut around the recorded quotation in his text of sura 80), and splits the result into 24
    files, 23 of 26 positions and the last of 11, so that each file fits one conversation.

Reads (all relative to the stage1-output folder, see --stage1-output)
    independent-coding/blind-packet-1.md ... blind-packet-6.md
        the October packets: 609 positions, one "## row | sura | phrase | who"
        block each.
    panel-packets/batch-*.md
        the verified al-Tabari passages ("### al-Tabari (printed page ...)")
        used to replace the 14 wrongly anchored al-Tabari windows.
    panel-extended-packets/batch-*.md
        the verified Ibn Atiyya passages ("### Ibn Atiyya (printed page ...)").
    ../data/al-muharrar-al-wajiz-ibn-atiyyah/80.json
        Ibn Atiyya's text of sura 80, because his passage on row 9 (80:15) is
        not in the extended packets; a window is cut around the recorded quote.

Writes
    <output_folder>/blind-packet-01-of-24.md ... blind-packet-24-of-24.md
        Nothing in them says what the first coder decided: every
        "preference found: ..." line of the October packets is absent, and the
        script asserts it. Packet 25 (the 15 positions added after October) is
        built by build_extra_packet_25_for_rows_17_19_63.py.

Run
    cd reference-coding/twelve-commentaries/stage1-output
    python -I <path to this script> <output_folder>
    (or from anywhere with --stage1-output <that folder>)

Feeds
    The packets coded by Gemini (results/gemini) and by the nine local Ollama
    models (results/<slug>), hence every agreement table in the SNM05 paper and
    the authors' article in preparation on the first twelve commentaries that rests on the 624-position second coding.
"""

import argparse
import glob
import json
import os
import re

# The 15 (row, commentator) positions whose October window was anchored in the
# wrong sura, as found by the second-coder comparison of 23 October 2026.
WRONGLY_ANCHORED_POSITIONS = {
    ("2", "tabari"), ("9", "tabari"), ("12", "tabari"), ("24", "tabari"),
    ("25", "tabari"), ("39", "tabari"), ("44", "tabari"), ("46", "tabari"),
    ("48", "tabari"), ("49", "tabari"), ("50", "tabari"), ("51", "tabari"),
    ("53", "tabari"), ("60", "tabari"), ("9", "ibnAtiyya"),
}

# Input locations inside the stage1-output folder.
OCTOBER_PACKET_PATTERN = "independent-coding/blind-packet-{number}.md"
OCTOBER_PACKET_COUNT = 6
TABARI_PASSAGES_GLOB = "panel-packets/batch-*.md"
TABARI_HEADING = "al-Tabari"
IBN_ATIYYA_PASSAGES_GLOB = "panel-extended-packets/batch-*.md"
IBN_ATIYYA_HEADING = "Ibn Atiyya"
IBN_ATIYYA_SURA_80_JSON = "../data/al-muharrar-al-wajiz-ibn-atiyyah/80.json"

# Row 9 (80:15), Ibn Atiyya: the recorded quote around which his window is cut,
# and the number of characters taken on each side of it (same width as the
# other windows, about 3,000 characters in all).
IBN_ATIYYA_ROW_9_QUOTE = "والقول الأول أرجح"
IBN_ATIYYA_ROW_9_ROW = "9"
WINDOW_HALF_WIDTH = 1500
# Spelling fold for the search of that quote only (since 5 Nov 2026): hamza and
# alif forms, ta marbuta, final ya and hamza on waw or ya are unified, one
# character for one, so the fold keeps every string length and an offset found
# in the folded text is the same offset in the unfolded text, from which the
# window is cut. The sura 80 text matches the quote as written, so the packet
# is unchanged (verified by a rebuild on 5 Nov 2026).
SPELLING_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})

# Arabic vowel marks (U+064B to U+0652), the superscript alif (U+0670) and the
# tatweel (U+0640): stripped from the Ibn Atiyya text as in the other packets,
# so that quotes match regardless of vocalisation. Since 5 Nov 2026 the
# invisible bidirectional controls (U+200E, U+200F, U+061C, U+202A-U+202E,
# U+2066-U+2069) are stripped with them and a non-breaking space (U+00A0) is
# written as a space; the sura 80 text holds none of these, so the packets
# are unchanged (verified by a rebuild on 5 Nov 2026).
VOWEL_MARKS = re.compile(r"[\u064b-\u0652\u0670\u0640\u200e\u200f\u061c\u202a-\u202e\u2066-\u2069]")
NON_BREAKING_SPACE = "\xa0"

# Expected number of positions: 67 phrases x 7 core commentators (469) plus
# 28 phrases x 5 extended commentators (140) present in October; rows 17, 19
# and 63 of the extended commentators (15 positions) came later, in packet 25.
EXPECTED_POSITIONS = 609
PACKET_COUNT = 24
OUTPUT_NAME = "blind-packet-{number:02d}-of-{count}.md"

# One position block in the October packets:
# "## row | sura and verses | phrase | who" followed by a "views:" line.
POSITION_HEADER = re.compile(r"## (\d+) \| ([^|]+)\| ([^|]+)\| (\w+)\n(views: [^\n]*)\n")
FIRST_CODER_MARKER = "preference found"


def number_in_file_name(path):
    """Return the first integer in a file's base name, for sorting batch-N.md
    files numerically (batch-10 after batch-9, not after batch-1)."""
    return int(re.search(r"(\d+)", os.path.basename(path)).group(1))


def read_text(path):
    """Return the whole content of a UTF-8 text file."""
    with open(path, encoding="utf8") as handle:
        return handle.read()


def verified_passages(file_glob, heading):
    """Collect the verified passages of one commentator from the panel packets.

    Takes the glob of the batch files and the commentator's heading as it
    appears in "### <heading> (printed page ...)". Returns {row: passage text}
    for every "## Passage <row> ..." section that has such a heading.
    """
    batch_files = sorted(glob.glob(file_glob), key=number_in_file_name)
    joined = "\n".join(read_text(path) for path in batch_files)
    passages = {}
    for section in re.split(r"\n(?=## Passage )", joined):
        header = re.match(r"## Passage (\d+) ", section)
        if not header:
            continue
        passage = re.search(
            r"### " + heading + r" \(printed page [^)]*\)[^\n]*\n(.*?)(?=\n### |\n## |\Z)",
            section, re.S)
        if passage:
            passages[header.group(1)] = passage.group(1).strip()
    return passages


def ibn_atiyya_window_on_row_9(sura_80_json_path):
    """Cut Ibn Atiyya's window on 80:15 (row 9) from his sura 80 text.

    The passage is not in the extended packets, so the window is 1,500
    characters each side of the recorded quote, vowel marks and bidirectional
    controls stripped, non-breaking spaces turned into spaces and whitespace
    collapsed, as in the other packets. The quote is searched with the
    length-preserving spelling fold applied to both the quote and the text,
    and the window is cut from the unfolded text at the offset found.
    Returns the window text.
    """
    with open(sura_80_json_path, encoding="utf8") as handle:
        sura_text = VOWEL_MARKS.sub("", json.load(handle)[0]["text"]).replace(NON_BREAKING_SPACE, " ")
    quote_index = sura_text.translate(SPELLING_FOLD).index(IBN_ATIYYA_ROW_9_QUOTE.translate(SPELLING_FOLD))
    window = sura_text[max(0, quote_index - WINDOW_HALF_WIDTH):quote_index + WINDOW_HALF_WIDTH]
    return re.sub(r"\s+", " ", window)


def october_positions(replacement_passages):
    """Read the 609 position blocks of the October packets, replacing the
    wrongly anchored windows.

    Takes {commentator code: {row: verified passage}} for "tabari" and
    "ibnAtiyya". Returns the list of position blocks (header, views line,
    window) in packet order, each ending with one newline. Asserts that no
    block carries a first-coder finding.
    """
    positions = []
    for packet_number in range(1, OCTOBER_PACKET_COUNT + 1):
        packet_text = read_text(OCTOBER_PACKET_PATTERN.format(number=packet_number))
        for block in re.split(r"\n(?=## )", packet_text):
            block = block.strip()
            if not block.startswith("## "):
                continue
            header = POSITION_HEADER.match(block)
            row, commentator = header.group(1), header.group(4)
            if (row, commentator) in WRONGLY_ANCHORED_POSITIONS:
                passages = replacement_passages[commentator]
                if row not in passages:
                    raise SystemExit(f"no replacement passage for row {row}, {commentator}")
                # Keep the header and views line, replace only the text window.
                block = header.group(0) + "\n" + passages[row] + "\n"
            # The October packets were built without first-coder findings; this
            # guards the blindness of the external coder all the same.
            if FIRST_CODER_MARKER in block:
                raise SystemExit(f"a first-coder finding is in the block of {header.group(0)}")
            positions.append(block.strip() + "\n")
    return positions


def write_packets(positions, output_folder):
    """Split the positions into PACKET_COUNT files of equal size (the last one
    may be shorter) and write them to output_folder. Returns positions per packet."""
    per_packet = -(-len(positions) // PACKET_COUNT)  # ceiling division
    for packet_index in range(PACKET_COUNT):
        chunk = positions[packet_index * per_packet:(packet_index + 1) * per_packet]
        if not chunk:
            break
        packet_number = packet_index + 1
        output_path = os.path.join(output_folder, OUTPUT_NAME.format(number=packet_number, count=PACKET_COUNT))
        with open(output_path, "w", encoding="utf8") as handle:
            handle.write(f"# Blind coding packet {packet_number} of {PACKET_COUNT} ({len(chunk)} positions)\n\n"
                         + "\n".join(chunk))
    return per_packet


def parse_arguments():
    """Parse the command line: the output folder, and optionally the
    stage1-output folder to read from (default: the current folder)."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_folder", help="folder that receives blind-packet-NN-of-24.md")
    parser.add_argument("--stage1-output", default=".",
                        help="the twelve-commentaries/stage1-output folder (default: current folder)")
    return parser.parse_args()


def main():
    """Rebuild the 24 packets and print the position count."""
    arguments = parse_arguments()
    output_folder = os.path.abspath(arguments.output_folder)
    os.chdir(arguments.stage1_output)
    replacement_passages = {
        "tabari": verified_passages(TABARI_PASSAGES_GLOB, TABARI_HEADING),
        "ibnAtiyya": verified_passages(IBN_ATIYYA_PASSAGES_GLOB, IBN_ATIYYA_HEADING),
    }
    replacement_passages["ibnAtiyya"][IBN_ATIYYA_ROW_9_ROW] = ibn_atiyya_window_on_row_9(IBN_ATIYYA_SURA_80_JSON)
    positions = october_positions(replacement_passages)
    if len(positions) != EXPECTED_POSITIONS:
        raise SystemExit(f"expected {EXPECTED_POSITIONS} positions, built {len(positions)}")
    per_packet = write_packets(positions, output_folder)
    print(len(positions), "positions,", per_packet, "per packet")


if __name__ == "__main__":
    main()
