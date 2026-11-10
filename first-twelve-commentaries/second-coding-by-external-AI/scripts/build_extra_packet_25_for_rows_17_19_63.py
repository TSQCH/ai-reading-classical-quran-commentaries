"""Build blind coding packet 25 (15 positions) for an external AI coder.

Purpose
    Rows 17, 19 and 63 of the five extended commentators (Ibn Atiyya,
    al-Tha'alibi, Abu Hayyan, Abu al-Su'ud, al-Nasafi) were added to the panel
    after the October 2026 packets were written, so packets 1 to 24 do not hold
    them. This script cuts a text window for each of these 3 x 5 = 15 positions
    and writes them as packet 25, in the same format as the other packets and
    without any first-coder finding.

Reads
    <panel_majority.json>
        the first coder's panel file (stage1-output/panel-majority.json): one
        record per phrase with n (row), sura, suraAr, unit, phrase, views and
        positions[<commentator>].quote, the quote on which the window is cut.
    <text_folder>/thaalibi.txt, abu-hayyan.txt, abu-saud.txt, nasafi.txt
        the four commentaries converted to plain text with Word (not part of this
        repository).
    <ibn_atiyya_folder>/<sura>.json
        Ibn Atiyya's al-Muharrar al-wajiz by sura
        (twelve-commentaries/data/al-muharrar-al-wajiz-ibn-atiyyah).

Writes
    <output_md>: blind-packet-25-of-25.md with the 15 positions.

Run
    python -I build_extra_packet_25_for_rows_17_19_63.py <panel_majority.json> <text_folder> <ibn_atiyya_folder> <output_md>

Feeds
    Packet 25 is coded with the other 24 (results/gemini/blind-packet-25-of-25.jsonl
    and the local models' positions.jsonl); the 624-position agreement figures
    in the JQS article and the SNM05 paper include its 15 positions.
"""

import argparse
import json
import os
import re

# The rows added to the extended panel after October, and the commentators
# coded for them.
EXTRA_ROWS = (17, 19, 63)
EXTENDED_COMMENTATORS = ("ibnAtiyya", "thaalibi", "abuHayyan", "abuSaud", "nasafi")

# Plain-text file per commentator inside the text folder (Ibn Atiyya comes
# from the per-sura JSON instead).
COMMENTARY_TEXT_FILES = {
    "thaalibi": "thaalibi.txt",
    "abuHayyan": "abu-hayyan.txt",
    "abuSaud": "abu-saud.txt",
    "nasafi": "nasafi.txt",
}

# Characters each side of the quote (about 3,000 in all, as in the other packets).
WINDOW_HALF_WIDTH = 1500

# The quote is searched by its first 40 characters, then shorter prefixes, so
# that a small difference in wording later in the quote does not lose the match.
QUOTE_PREFIX_LENGTHS = (40, 25, 15, 10)

# Arabic vowel marks (U+064B to U+0652), the superscript alif (U+0670) and the
# tatweel (U+0640): stripped from text and quotes alike so that they match
# regardless of vocalisation, as in the other packets. Since 5 Nov 2026 the
# invisible bidirectional controls (U+200E, U+200F, U+061C, U+202A-U+202E,
# U+2066-U+2069) are stripped with them and a non-breaking space (U+00A0) is
# written as a space, as the other packet builders do; the texts of packet 25
# hold none of these, so the packet is unchanged (verified by a rebuild on
# 5 Nov 2026).
VOWEL_MARKS = re.compile(r"[ً-ْٰـ‎‏؜‪-‮⁦-⁩]")
NON_BREAKING_SPACE = "\xa0"

# Qur'anic bracket characters around a phrase, stripped before a phrase word is
# used as a search key.
QURAN_BRACKETS = "﴿﴾"

PACKET_NUMBER = 25
PACKET_COUNT = 25


def normalise(text):
    """Strip vowel marks and bidirectional controls, turn non-breaking spaces into
    spaces and collapse whitespace, so that a quote and the commentary text match
    character for character."""
    return re.sub(r"\s+", " ", VOWEL_MARKS.sub("", text).replace(NON_BREAKING_SPACE, " "))


def load_commentary_texts(text_folder):
    """Read and normalise the four plain-text commentaries.
    Returns {commentator code: normalised text}. Undecodable bytes left by the
    Word conversion are ignored."""
    texts = {}
    for commentator, file_name in COMMENTARY_TEXT_FILES.items():
        with open(os.path.join(text_folder, file_name), encoding="utf8", errors="ignore") as handle:
            texts[commentator] = normalise(handle.read())
    return texts


def ibn_atiyya_sura_text(ibn_atiyya_folder, sura):
    """Return Ibn Atiyya's normalised text of one sura, joined from the
    verse-by-verse JSON records."""
    with open(os.path.join(ibn_atiyya_folder, f"{sura}.json"), encoding="utf8") as handle:
        return normalise(" ".join(record["text"] for record in json.load(handle)))


def find_quote(text, quote, phrase):
    """Locate the recorded quote in the commentary text.

    Tries the first 40, 25, 15 and 10 characters of the quote in turn. If none
    is found (the quote's wording differs in this copy of the commentary), falls
    back to the last word of the disputed phrase, which the commentator must
    cite. Returns the character index, or -1 if nothing matches.
    """
    for prefix_length in QUOTE_PREFIX_LENGTHS:
        index = text.find(quote[:prefix_length])
        if index >= 0:
            return index
    phrase_last_word = normalise(phrase).split()[-1].strip(QURAN_BRACKETS)
    return text.find(phrase_last_word)


def position_block(record, commentator, window):
    """Format one position as in the other packets: the header line
    "## row | sura unit | phrase | who", the "views:" line, then the window."""
    views_line = " ; ".join(view["id"] + " = " + view["label_ar"] for view in record["views"])
    return (f"## {record['n']} | {record['suraAr']} {record['unit']} | {record['phrase']} | {commentator}\n"
            f"views: {views_line}\n\n{window}\n")


def build_positions(panel_records, commentary_texts, ibn_atiyya_folder):
    """Cut the window of every extended commentator on the extra rows.
    Returns the list of formatted position blocks in panel order."""
    positions = []
    for record in panel_records:
        if record["n"] not in EXTRA_ROWS:
            continue
        for commentator in EXTENDED_COMMENTATORS:
            quote = normalise(record["positions"][commentator]["quote"]).strip()
            if commentator == "ibnAtiyya":
                text = ibn_atiyya_sura_text(ibn_atiyya_folder, record["sura"])
            else:
                text = commentary_texts[commentator]
            index = find_quote(text, quote, record["phrase"])
            if index < 0:
                raise SystemExit(f"quote not found: row {record['n']}, {commentator}, {quote[:30]}")
            window = text[max(0, index - WINDOW_HALF_WIDTH):index + WINDOW_HALF_WIDTH]
            positions.append(position_block(record, commentator, window))
    return positions


def parse_arguments():
    """Parse the four positional arguments: panel file, text folder,
    Ibn Atiyya folder, output file."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("panel_majority", help="stage1-output/panel-majority.json")
    parser.add_argument("text_folder", help="folder with thaalibi.txt, abu-hayyan.txt, abu-saud.txt, nasafi.txt")
    parser.add_argument("ibn_atiyya_folder", help="folder with Ibn Atiyya's <sura>.json files")
    parser.add_argument("output_md", help="the packet file to write (blind-packet-25-of-25.md)")
    return parser.parse_args()


def main():
    """Build packet 25 and print how many positions it holds."""
    arguments = parse_arguments()
    with open(arguments.panel_majority, encoding="utf8") as handle:
        panel_records = json.load(handle)
    commentary_texts = load_commentary_texts(arguments.text_folder)
    positions = build_positions(panel_records, commentary_texts, arguments.ibn_atiyya_folder)
    with open(arguments.output_md, "w", encoding="utf8") as handle:
        handle.write(f"# Blind coding packet {PACKET_NUMBER} of {PACKET_COUNT} ({len(positions)} positions)\n\n"
                     + "\n".join(positions))
    print(len(positions), "positions written to", arguments.output_md)


if __name__ == "__main__":
    main()
