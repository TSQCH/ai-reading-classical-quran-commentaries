"""Draw the stratified sample of 100 positions for the independent human coding (SNM05, Section 6.3).

Purpose
    The paper promises an independent human coding of a stratified sample of 100 positions,
    about seven per commentary and drawn so that every type of position, including the rare
    preference and reconciliation, is represented, coded blind by two readers under the same
    rule. This script draws that sample from the reference coding, writes one Excel answer
    workbook per reader with the same text windows the language models read (no reference
    answer, but see "Known limit of the draw"), and keeps the reference answers in a separate key file that
    is never given to the readers.

Reads
    ../../../reference-coding/twelve-commentaries/stage1-output/panel-majority.json
        the reference coding of the 624 positions on the first twelve commentaries: one record
        per disputed point (n = row, sura, unit, phrase, views) with positions[<who>] =
        {type, holds, quote, page, ...}.
    ../../blind-coding/results/claude/blind-packet-26-hawwari.jsonl and -27-himyan.jsonl
        the reference coding of the 134 positions on al-Hawwari and Himyan al-zad.
    ../../../first-twelve-commentaries/second-coding-by-external-AI/data/blind-packet-*.md
    ../../blind-coding/data/blind-packet-26-hawwari.md and -27-himyan.md
        the packets: the text window of every position, as served to the models. Packet 25
        carries the 15 windows of rows 17, 19 and 63 for the five later commentaries.

Writes (in ../, the human-coding folder)
    send-to-reader-1/SNM05-human-coding-sample-100-positions-reader-1.xlsx
    send-to-reader-2/SNM05-human-coding-sample-100-positions-reader-2.xlsx
        identical answer workbooks, one per reader, each in the folder that is sent to that
        reader together with the Arabic instructions: serial number, row, sura and verses,
        disputed phrase, commentator, candidate views, the text window, and four empty answer
        columns (type with a drop-down list, views held, verbatim quotation, note).
    sample-key/SNM05-human-coding-sample-100-reference-key.json
        the sampled positions with the reference type and views held. NOT for the readers.
    sample-key/SNM05-human-coding-sample-100-composition.md
        the composition of the sample by commentary and type, for the paper.

Run
    python scripts/build_human_coding_sample_100_positions.py
    (python -I works when openpyxl was installed as the README says; use plain python if it
    sits in the user site-packages, which -I hides)

How the sample is drawn
    Every commentary gets SAMPLE_PER_COMMENTARY positions, al-Tabari and al-Razi one more each
    (the two foundational commentaries, read on all 67 points), which gives 100. Within a
    commentary one position of every type that commentary has in the reference coding is
    drawn first, so that preference, reconciliation and silence are represented wherever they
    occur; the remaining places are filled at random from the rest. The random generator is
    seeded with RANDOM_SEED so that the draw can be reproduced exactly. The final order of the
    100 positions is shuffled with the same generator, so that neither the commentary nor the
    type can be guessed from the position of a row in the workbook.

Known limit of the draw
    Two windows of the first set carry no text, only the packet builder's note that no passage
    was found (row 36, Ibn Juzayy, and row 43, al-Baydawi). They are the only positions those
    two commentaries have coded silent, so the draw above takes both, and the note shows the
    readers the answer. The draw was made and sent as it stands; these two positions are left
    out when the readers' answers are compared with the reference coding.
    Run on the deposited packets, the workbooks show the editors' footnotes replaced by the mark
    of README part A; the workbooks sent to the readers carried the windows as served.
"""

import collections
import glob
import json
import os
import random
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HUMAN_CODING_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER_FOLDER = os.path.dirname(HUMAN_CODING_FOLDER)
CLAUDE_FOLDER = os.path.dirname(PAPER_FOLDER)  # the repository root (named after the authors' working folder)
REFERENCE_PANEL_FILE = os.path.join(CLAUDE_FOLDER, "reference-coding", "twelve-commentaries",
                                    "stage1-output", "panel-majority.json")
OMAN_REFERENCE_FILES = [os.path.join(PAPER_FOLDER, "blind-coding", "results", "claude", name)
                        for name in ("blind-packet-26-hawwari.jsonl", "blind-packet-27-himyan.jsonl")]
FIRST_SET_PACKETS_GLOB = os.path.join(CLAUDE_FOLDER, "first-twelve-commentaries",
                                      "second-coding-by-external-AI", "data", "blind-packet-*.md")
OMAN_PACKETS_GLOB = os.path.join(PAPER_FOLDER, "blind-coding", "data", "blind-packet-2[67]-*.md")
KEY_FOLDER = os.path.join(HUMAN_CODING_FOLDER, "sample-key")
WORKBOOK_NAME = os.path.join("send-to-reader-{reader}", "SNM05-human-coding-sample-100-positions-reader-{reader}.xlsx")
# Each send-to-reader-N folder holds everything one reader receives and nothing else.
READERS = (1, 2)

RANDOM_SEED = 20261105  # the date of the draw, so that it can be reproduced
SAMPLE_PER_COMMENTARY = 7
EXPECTED_POSITIONS = 758  # 624 positions of the first set and 134 of the second
SAMPLE_SIZE = 100
WORKBOOK_ROW_HEIGHT = 220  # points: room for a window of about 3,000 characters
KEY_FILE_NAME = "SNM05-human-coding-sample-100-reference-key.json"
COMPOSITION_FILE_NAME = "SNM05-human-coding-sample-100-composition.md"
EXTRA_FOR = ("tabari", "razi")  # one more each, to reach 100
TYPES = ("prefers", "single", "combines", "lists_no_choice", "silent")

# Arabic names shown to the readers; the codes are those of the packets.
COMMENTATOR_NAMES_AR = {
    "hawwari": "هود بن محكم الهواري", "tabari": "الطبري", "ibnAtiyya": "ابن عطية",
    "razi": "فخر الدين الرازي", "qurtubi": "القرطبي", "baydawi": "البيضاوي", "nasafi": "النسفي",
    "ibnJuzayy": "ابن جزي", "khazin": "الخازن", "abuHayyan": "أبو حيان", "thaalibi": "الثعالبي",
    "abuSaud": "أبو السعود", "himyan": "محمد بن يوسف أطفيش (هميان الزاد)", "ibnAshur": "ابن عاشور",
}
# The five types as the readers will enter them (drop-down list in the workbook).
TYPE_LABELS_AR = {
    "prefers": "يرجّح قولاً", "single": "قول واحد", "combines": "يجمع بين الأقوال",
    "lists_no_choice": "يذكر الأقوال دون ترجيح", "silent": "لم يتعرض للمسألة",
}
HEADERS_AR = ("م", "رقم الموضع", "السورة والآيات", "العبارة المختلف فيها", "المفسر",
              "الأقوال المرشحة", "نص المفسر (النافذة)",
              "النوع", "الأقوال التي يحملها", "الاقتباس الحرفي", "ملاحظة")
COLUMN_WIDTHS = (5, 10, 16, 30, 22, 45, 90, 24, 18, 45, 30)
ANSWER_COLUMNS = (8, 9, 10, 11)  # 1-based: the four columns the reader fills
ANSWER_FILL = PatternFill("solid", fgColor="FFF2CC")  # pale yellow: cells to fill
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
FONT_NAME = "Arial"

PACKET_HEADER = re.compile(r"^## (\d+) \| (.+?) \| (.+?) \| (\w+)\s*$")


def read_reference_positions():
    """Return every reference position as a dict: row, who, type, holds, unit, phrase, views."""
    positions = []
    with open(REFERENCE_PANEL_FILE, encoding="utf8") as handle:
        panel = json.load(handle)
    points = {}  # row -> (sura+unit, phrase, views text), reused for the Oman positions
    for record in panel:
        unit = f"{record['suraAr']} {record['unit']}"
        views_text = " ; ".join(f"{view['id']} = {view['label_ar']}" for view in record["views"])
        points[record["n"]] = (unit, record["phrase"], views_text)
        for who, coding in record["positions"].items():
            positions.append(dict(row=record["n"], who=who, type=coding["type"], holds=coding["holds"],
                                  unit=unit, phrase=record["phrase"], views=views_text))
    for path in OMAN_REFERENCE_FILES:
        with open(path, encoding="utf8") as handle:
            for line in handle:
                if not line.startswith("{"):
                    continue
                coding = json.loads(line)
                unit, phrase, views_text = points[coding["row"]]
                positions.append(dict(row=coding["row"], who=coding["who"], type=coding["type"],
                                      holds=coding["holds"], unit=unit, phrase=phrase, views=views_text))
    return positions


def read_windows():
    """Return {(row, who): window text} from every packet; packet 25 overrides packets 1-24."""
    windows = {}
    packet_files = sorted(glob.glob(FIRST_SET_PACKETS_GLOB)) + sorted(glob.glob(OMAN_PACKETS_GLOB))
    for path in packet_files:
        current_key, lines = None, []
        with open(path, encoding="utf8") as handle:
            for line in handle:
                header = PACKET_HEADER.match(line)
                if header:
                    if current_key:
                        windows[current_key] = "\n".join(lines).strip()
                    current_key, lines = (int(header.group(1)), header.group(4)), []
                elif current_key and not line.startswith("views:"):
                    lines.append(line.rstrip("\n"))
        if current_key:
            windows[current_key] = "\n".join(lines).strip()
    return windows


def draw_sample(positions, generator):
    """Stratified draw: per commentary, one of each type present first, then random fill."""
    by_commentator = collections.defaultdict(list)
    for position in positions:
        by_commentator[position["who"]].append(position)
    sample = []
    for who, candidates in sorted(by_commentator.items()):
        quota = SAMPLE_PER_COMMENTARY + (1 if who in EXTRA_FOR else 0)
        chosen = []
        for type_name in TYPES:
            of_type = [candidate for candidate in candidates if candidate["type"] == type_name]
            if of_type:
                chosen.append(generator.choice(of_type))
        remaining = [candidate for candidate in candidates if candidate not in chosen]
        chosen.extend(generator.sample(remaining, quota - len(chosen)))
        sample.extend(chosen)
    generator.shuffle(sample)
    return sample


def write_workbook(sample, windows, path):
    """Write one reader's answer workbook: the material, and empty answer columns."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "المواضع"
    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = "A2"
    for column, (header, width) in enumerate(zip(HEADERS_AR, COLUMN_WIDTHS), start=1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.font = Font(name=FONT_NAME, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(column)].width = width
    for serial, position in enumerate(sample, start=1):
        values = (serial, position["row"], position["unit"], position["phrase"],
                  COMMENTATOR_NAMES_AR[position["who"]], position["views"],
                  windows[(position["row"], position["who"])], "", "", "", "")
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=serial + 1, column=column, value=value)
            cell.font = Font(name=FONT_NAME, size=11)
            cell.alignment = Alignment(vertical="top", wrap_text=True, readingOrder=2)
            if column in ANSWER_COLUMNS:
                cell.fill = ANSWER_FILL
        sheet.row_dimensions[serial + 1].height = WORKBOOK_ROW_HEIGHT
    type_list = DataValidation(type="list", formula1='"' + ",".join(TYPE_LABELS_AR.values()) + '"',
                               allow_blank=True, showErrorMessage=True,
                               errorTitle="النوع", error="اختاري أحد الأنواع الخمسة من القائمة")
    sheet.add_data_validation(type_list)
    type_list.add(f"H2:H{len(sample) + 1}")
    workbook.save(path)


def write_key_and_composition(sample):
    """Write the reference answers (never for the readers) and the composition of the sample."""
    os.makedirs(KEY_FOLDER, exist_ok=True)
    key = [dict(serial=serial, row=position["row"], who=position["who"], reference_type=position["type"],
                reference_holds=position["holds"])
           for serial, position in enumerate(sample, start=1)]
    with open(os.path.join(KEY_FOLDER, KEY_FILE_NAME), "w", encoding="utf8") as handle:
        handle.write(json.dumps(key, ensure_ascii=False, indent=1))
    counts = collections.Counter((position["who"], position["type"]) for position in sample)
    lines = ["# Composition of the 100-position human-coding sample (seed %d)" % RANDOM_SEED, "",
             "| Commentary | " + " | ".join(TYPES) + " | Total |", "|---|" + "---|" * (len(TYPES) + 1)]
    for who in sorted({position["who"] for position in sample}):
        row_counts = [counts[(who, type_name)] for type_name in TYPES]
        lines.append(f"| {who} | " + " | ".join(str(count) for count in row_counts) + f" | {sum(row_counts)} |")
    totals = [sum(counts[(commentator, type_name)] for commentator in COMMENTATOR_NAMES_AR) for type_name in TYPES]
    lines.append("| **Total** | " + " | ".join(str(count) for count in totals) + f" | {sum(totals)} |")
    with open(os.path.join(KEY_FOLDER, COMPOSITION_FILE_NAME), "w", encoding="utf8") as handle:
        handle.write("\n".join(lines) + "\n")
    return lines


def main():
    """Draw the sample, write the two workbooks, the key and the composition table."""
    positions = read_reference_positions()
    windows = read_windows()
    missing = [(position["row"], position["who"]) for position in positions
               if (position["row"], position["who"]) not in windows]
    if len(positions) != EXPECTED_POSITIONS or missing:
        raise SystemExit(f"expected {EXPECTED_POSITIONS} positions, each with a window; "
                         f"found {len(positions)}, without a window: {missing}")
    sample = draw_sample(positions, random.Random(RANDOM_SEED))
    if len(sample) != SAMPLE_SIZE:
        raise SystemExit(f"the draw gave {len(sample)} positions, not {SAMPLE_SIZE}")
    for reader in READERS:
        os.makedirs(os.path.join(HUMAN_CODING_FOLDER, f"send-to-reader-{reader}"), exist_ok=True)
        write_workbook(sample, windows, os.path.join(HUMAN_CODING_FOLDER, WORKBOOK_NAME.format(reader=reader)))
    print("\n".join(write_key_and_composition(sample)))


if __name__ == "__main__":
    main()
