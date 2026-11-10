"""Build the blind-coding packets for al-Hawwari and Himyan al-zad (packets 26 and 27).

Purpose
    Produces the two packets of commentary windows that every blind coder (Gemini CLI and the
    nine Ollama models) reads for the 134 Oman positions of the SNM05 paper, in the same format
    as the JQS packets: a header "## <row> | <sura unit> | <phrase> | <who>", a "views:" line
    listing the candidate views, then a window of the commentator's text with vowel marks
    stripped. Paper Section 3.4 (The packets) describes the result; Table 2 is computed on it.

Reads
    <panel-majority.json>   the 67 disputed points of Juz' Amma with their unit, phrase and
                            candidate views (argument; the stage-1 output of the JQS project).
    sources/altafsir-com/hawwari-tafsir-kitab-allah-al-aziz.txt
    sources/altafsir-com/atfayyish-himyan-al-zad.txt
                            the downloaded commentaries, "=== sura:first-last ===" passages
                            (from scripts/download_ibadi_tafsirs_juz_amma_from_altafsir_com.py).

Writes
    blind-coding/data/blind-packet-26-hawwari.md   67 positions, who = hawwari
    blind-coding/data/blind-packet-27-himyan.md    67 positions, who = himyan
    (or the same two names under --out-dir), and prints one line per packet saying how many
    windows were anchored on the full phrase, on 3, 2 or 1 words, or fell back to the unit.

Run
    python -I scripts/build_blind_packets_hawwari_and_himyan.py <panel-majority.json> [--out-dir FOLDER]

How a window is chosen (v02, 4 Nov 2026)
    The unit ranges in panel-majority.json are al-Tabari's passage ranges and do not always
    contain the verse of the disputed phrase (row 28 "wa-dhakara isma rabbihi fa-salla" is
    Q. 87:15 while the unit is 87:16-19). The window is therefore centred on the best match of
    the phrase: the full phrase, then its last three words, then its last two, searched first
    in the unit's passages and then in the whole sura; then the last word alone, inside the
    unit only; and if nothing matches, the first 3,000 characters of the unit's passages. For
    the search only, spelling is folded (hamza forms, alif variants, ta marbuta, final ya), so
    that the website's orthography does not defeat the match. The window is WINDOW_HALF_WIDTH
    characters on each side of the match (the whole passage set when it is shorter).
"""

import argparse
import json
import os
import re

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_FOLDER = os.path.join(PROJECT_FOLDER, "sources", "altafsir-com")
DEFAULT_OUTPUT_FOLDER = os.path.join(PROJECT_FOLDER, "blind-coding", "data")

# packet number -> (commentator code used in the packet header, source file slug)
PACKETS = (
    (26, "hawwari", "hawwari-tafsir-kitab-allah-al-aziz"),
    (27, "himyan", "atfayyish-himyan-al-zad"),
)
WINDOW_HALF_WIDTH = 1500  # characters each side of the matched phrase
FALLBACK_WINDOW_LENGTH = 3000  # when no phrase match is found: the start of the unit's passages

# Vowel marks (fathatan to sukun, U+064B-U+0652), the superscript alif (U+0670) and the tatweel
# (U+0640) are removed so that string matching is not defeated by variant vocalisation, and the
# coders read unvoweled text, as a scholar reads most printed editions. Since 5 Nov 2026 the
# invisible bidirectional controls (U+200E, U+200F, U+061C, U+202A-U+202E, U+2066-U+2069) are
# removed with them, and a non-breaking space (U+00A0) counts as a space; the downloaded sources
# of 4 Nov 2026 contain none of these, so the packets are unchanged (verified by a rebuild).
VOWEL_MARKS = re.compile(r"[ً-ْٰـ‎‏؜‪-‮⁦-⁩]")
NON_BREAKING_SPACE = "\xa0"
# Spelling folds applied to the search key and the searched text only, never to the window written out.
SPELLING_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
QURAN_BRACKETS = "﴿﴾"  # ornate brackets around the phrase in panel-majority.json, not part of the words
PASSAGE_PATTERN = re.compile(r"=== (\d+):(\d+)-(\d+) ===\n(.*?)(?=\n=== |\Z)", re.S)


def strip_vowels(text):
    """Remove vowel marks, tatweel and bidirectional controls, turn non-breaking spaces into spaces,
    and collapse runs of spaces and tabs to one space."""
    return re.sub(r"[ \t]+", " ", VOWEL_MARKS.sub("", text).replace(NON_BREAKING_SPACE, " ")).strip()


def fold_spelling(text):
    """Return the text with hamza, alif, ta marbuta and ya variants folded, for searching only."""
    return text.translate(SPELLING_FOLD)


def load_passages(slug):
    """Return the passages of one downloaded commentary as (sura, first verse, last verse, unvoweled text)."""
    with open(os.path.join(SOURCES_FOLDER, slug + ".txt"), encoding="utf8") as handle:
        text = handle.read()
    passages = []
    for match in PASSAGE_PATTERN.finditer(text):
        passages.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), strip_vowels(match.group(4))))
    return passages


def cut_window(passages, point):
    """Return (window text, number of words the window was anchored on) for one disputed point.

    The anchor count is len(phrase words), 3, 2 or 1 for a phrase match, 0 for the unit fallback.
    Search order: phrase (full, last 3, last 2 words) in the unit's passages; the same in the
    whole sura; the last word alone inside the unit; then the unit's passages themselves.
    A single word is accepted only inside the unit, never across the sura, because one word
    recurs too often in a sura to locate the discussion.
    """
    sura_text, verse_range = point["unit"].split(":")
    first_verse, last_verse = (int(verse) for verse in verse_range.split("-"))
    sura = int(sura_text)
    unit_text = "\n".join(passage[3] for passage in passages
                          if passage[0] == sura and not (passage[2] < first_verse or passage[1] > last_verse))
    sura_whole_text = "\n".join(passage[3] for passage in passages if passage[0] == sura)
    phrase_words = [word.strip(QURAN_BRACKETS) for word in strip_vowels(point["phrase"]).split()]
    search_plan = (
        (unit_text, (len(phrase_words), 3, 2)),
        (sura_whole_text, (len(phrase_words), 3, 2)),
        (unit_text, (1,)),
    )
    for searched_text, word_counts in search_plan:
        folded_text = fold_spelling(searched_text)
        for word_count in word_counts:
            if word_count > len(phrase_words):
                continue
            key = fold_spelling(" ".join(phrase_words[-word_count:]))
            # A one-word phrase (e.g. "kalla") is looked for first as a quoted lemma: "{ kalla",
            # "qawluhu kalla", "﴿kalla", and only then as a bare word.
            candidates = ["{ " + key, "قوله " + key, "﴿" + key, key] if word_count == 1 else [key]
            for candidate in candidates:
                position = folded_text.find(candidate)
                if position >= 0:
                    return searched_text[max(0, position - WINDOW_HALF_WIDTH):position + len(candidate) + WINDOW_HALF_WIDTH], word_count
    return unit_text[:FALLBACK_WINDOW_LENGTH], 0


def format_position(point, who, window):
    """Return one packet entry: header line, views line, blank line, window."""
    views = " ; ".join(view["id"] + " = " + view["label_ar"] for view in point["views"])
    return f"## {point['n']} | {point['suraAr']} {point['unit']} | {point['phrase']} | {who}\nviews: {views}\n\n{window}\n"


def build_packet(packet_number, who, passages, points, output_folder):
    """Write one packet file and print how its windows were anchored."""
    entries = []
    anchor_counts = {}
    for point in points:
        window, anchor_words = cut_window(passages, point)
        anchor_counts[anchor_words] = anchor_counts.get(anchor_words, 0) + 1
        if not window.strip():
            raise ValueError(f"empty window for {who} row {point['n']} unit {point['unit']}")
        entries.append(format_position(point, who, window))
    output_path = os.path.join(output_folder, f"blind-packet-{packet_number}-{who}.md")
    with open(output_path, "w", encoding="utf8") as handle:
        handle.write(f"# Blind coding packet {packet_number} ({who}, {len(entries)} positions)\n\n" + "\n".join(entries))
    print(who, len(entries), "positions; anchored on full phrase / 3 / 2 / 1 words / unit fallback:", anchor_counts, "->", output_path)


def main():
    """Parse the arguments, load the two commentaries and build packets 26 and 27."""
    parser = argparse.ArgumentParser(description="Build blind-coding packets 26 (al-Hawwari) and 27 (Himyan al-zad).")
    parser.add_argument("panel_majority_json", help="panel-majority.json with the 67 disputed points")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_FOLDER,
                        help=f"folder for the two packet files (default: {DEFAULT_OUTPUT_FOLDER})")
    arguments = parser.parse_args()
    os.makedirs(arguments.out_dir, exist_ok=True)
    with open(arguments.panel_majority_json, encoding="utf8") as handle:
        points = json.load(handle)
    for packet_number, who, slug in PACKETS:
        build_packet(packet_number, who, load_passages(slug), points, arguments.out_dir)


if __name__ == "__main__":
    main()
