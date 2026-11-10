"""Download the Ibadi commentaries on Juz' Amma (Q. 78-114) as plain text from altafsir.com.

Purpose
    Obtains the digital text of the two Ibadi commentaries (and Atfayyish's shorter Taysir)
    read for the SNM05 paper, "AI-powered reading of Qur'an commentaries" (paper Section 3.2,
    The material). altafsir.com (Royal Aal al-Bayt Institute for Islamic Thought, Jordan)
    renders each commentary passage by passage: one web page covers a run of consecutive
    verses. The script walks each sura from verse 1, reads how many verses the page covers,
    saves the passage, and continues from the next verse, one request per second.

Reads
    Nothing local. Fetches pages from
    https://www.altafsir.com/Tafasir.asp?tMadhNo=6&tTafsirNo=<n>&tSoraNo=<sura>&tAyahNo=<verse>...
    (tMadhNo=6 is the Ibadi school; tTafsirNo per commentary in TAFSIRS below).

Writes
    sources/altafsir-com/<slug>.txt   one file per commentary, with a two-line header (title;
                                      "source: altafsir.com, tTafsirNo=<n>, downloaded <date>")
                                      and a "=== <sura>:<first>-<last> ===" marker before each
                                      passage; a commentary whose file already reaches sura 114
                                      is skipped, and a file cut short by an interruption is
                                      continued in append mode from the passage after its last
                                      complete one (since 5 Nov 2026; before, it was rewritten
                                      from sura 78).
    sources/altafsir-com/download.log progress and retry messages, appended on every run.

Run
    python -I scripts/download_ibadi_tafsirs_juz_amma_from_altafsir_com.py [slug ...]
    Without arguments the two commentaries in DEFAULT_SLUGS are downloaded:
    hawwari-tafsir-kitab-allah-al-aziz and atfayyish-himyan-al-zad. The third slug,
    atfayyish-taysir-al-tafsir, can be named but is not a default: altafsir.com lists
    Atfayyish's Taysir al-tafsir without any text (every page comes back empty; the empty
    download of 4 Nov 2026 is kept in sources/altafsir-com/previous-versions).
    Options: --download-date YYYY-MM-DD   the date written in the file header (default: today),
                                          so that a re-run can reproduce a file byte for byte
             --no-timestamp               write the header without the ", downloaded <date>" part

Empty pages (since 5 Nov 2026)
    A fetched page that yields no commentary text abandons that commentary: a warning naming
    the commentary and verse is logged, nothing is written for it (a file created in this run
    is removed again; passages saved by an earlier run are kept), and the run goes on with the
    next slug requested. At the end the script exits with code EXIT_CODE_SLUG_ABANDONED (1)
    when any slug was abandoned, so a single-slug run on an empty commentary fails too.
    Before 5 Nov 2026 an empty passage was written and only counted; earlier on 5 Nov 2026
    the first empty page stopped the whole run, whatever slugs were still to come.

Note
    The digital text is used for reading and for building the blind-coding packets
    (scripts/build_blind_packets_hawwari_and_himyan.py). Quotations in the paper are cited
    from the printed editions, not from this download.
"""

import argparse
import html
import os
import re
import sys
import time
import urllib.request

PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FOLDER = os.path.join(PROJECT_FOLDER, "sources", "altafsir-com")
LOG_PATH = os.path.join(OUTPUT_FOLDER, "download.log")

# slug -> (altafsir.com tTafsirNo, Arabic title and author as shown on the site)
TAFSIRS = {
    "hawwari-tafsir-kitab-allah-al-aziz": (48, "تفسير كتاب الله العزيز، هود بن محكم الهواري (ت نحو 280هـ)"),
    "atfayyish-himyan-al-zad": (49, "هميان الزاد إلى دار المعاد، محمد بن يوسف اطفيش (ت 1332هـ)"),
    "atfayyish-taysir-al-tafsir": (50, "تيسير التفسير، محمد بن يوسف اطفيش (ت 1332هـ)"),
}
# Downloaded when no slug is named. Taysir al-tafsir is left out: altafsir.com has no text for it
# (see Empty pages above); it can still be named on the command line.
DEFAULT_SLUGS = ["hawwari-tafsir-kitab-allah-al-aziz", "atfayyish-himyan-al-zad"]
EXIT_CODE_SLUG_ABANDONED = 1  # exit code when at least one requested commentary had an empty page

# Number of verses in each sura of Juz' Amma (Q. 78 to 114), used to know when a sura is complete.
VERSES_PER_SURA = {
    78: 40, 79: 46, 80: 42, 81: 29, 82: 19, 83: 36, 84: 25, 85: 22, 86: 17, 87: 19, 88: 26, 89: 30,
    90: 20, 91: 15, 92: 21, 93: 11, 94: 8, 95: 8, 96: 19, 97: 5, 98: 8, 99: 8, 100: 11, 101: 11,
    102: 8, 103: 3, 104: 9, 105: 5, 106: 4, 107: 7, 108: 3, 109: 6, 110: 3, 111: 5, 112: 4,
    113: 5, 114: 6,
}
FIRST_SURA = 78
LAST_SURA = 114

PAGE_URL = ("https://www.altafsir.com/Tafasir.asp?tMadhNo=6&tTafsirNo={tafsir_no}&tSoraNo={sura}"
            "&tAyahNo={verse}&tDisplay=yes&UserProfile=0&LanguageId=1")
USER_AGENT = "Mozilla/5.0 (research download, one page per second)"
PAGE_ENCODING = "windows-1256"  # altafsir.com serves Arabic in the Windows Arabic code page, not UTF-8
REQUEST_TIMEOUT_SECONDS = 60
FETCH_ATTEMPTS = 4
RETRY_WAIT_SECONDS = 10  # multiplied by the attempt number: 10, 20, 30 s
SECONDS_BETWEEN_PAGES = 1  # politeness pause so the site is not hammered

# The page lists each verse it covers as a styled link; counting them tells how far the passage reaches.
VERSE_LINK_PATTERN = r"class='TextAyah' style='TEXT-DECORATION: none'"
# The commentary text sits in nested font tags; the inner one carries the Arabic.
COMMENTARY_TEXT_PATTERN = r"<font class='TextResultArabic'><font color='black'>(.*?)</font></font>"
# A file that already carries a marker for sura 114 holds the whole juz' and is not downloaded again.
COMPLETE_FILE_MARKER = f"=== {LAST_SURA}:"
# The marker written before each passage; the last one in an interrupted file says where to resume.
PASSAGE_MARKER_PATTERN = re.compile(r"^=== (\d+):(\d+)-(\d+) ===$", re.M)
PASSAGE_TERMINATOR = "\n\n"  # written after every passage; a file not ending with it was cut mid-passage
DATE_FORMAT = "%Y-%m-%d"  # the download date in the file header, e.g. 2026-11-04
HEADER_WITH_DATE = "# {title}\n# source: altafsir.com, tTafsirNo={tafsir_no}, downloaded {date}\n\n"
HEADER_WITHOUT_DATE = "# {title}\n# source: altafsir.com, tTafsirNo={tafsir_no}\n\n"
EMPTY_PAGE_WARNING = "{slug} {sura}:{verse}: the page yields no commentary text; nothing written for it, slug abandoned"
# Invisible bidirectional controls (U+200E, U+200F, U+061C, U+202A-U+202E, U+2066-U+2069) are
# dropped from the page text and a non-breaking space (U+00A0) is written as a space, so that
# the saved text holds nothing that string matching cannot see. Added 5 Nov 2026; the files
# downloaded on 4 Nov 2026 contain none of these characters, so they are unaffected.
BIDI_CONTROLS = re.compile(r"[‎‏؜‪-‮⁦-⁩]")
NON_BREAKING_SPACE = "\xa0"


class EmptyPage(Exception):
    """Raised by download_commentary when a page has no commentary text; the message names slug and verse."""


def log_message(log_file, message):
    """Print a progress message and append it to the download log, flushing both at once."""
    print(message, flush=True)
    log_file.write(message + "\n")
    log_file.flush()


def fetch_page(log_file, tafsir_no, sura, verse):
    """Return the decoded HTML of the altafsir.com page for one commentary at one verse.

    Retries FETCH_ATTEMPTS times with a growing pause, because the site drops connections now
    and then; exits the script if every attempt fails, so that no gap is silently written.
    """
    url = PAGE_URL.format(tafsir_no=tafsir_no, sura=sura, verse=verse)
    for attempt in range(FETCH_ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.read().decode(PAGE_ENCODING, "replace")
        except Exception as error:
            log_message(log_file, f"  retry {attempt + 1} {sura}:{verse} {error}")
            time.sleep(RETRY_WAIT_SECONDS * (attempt + 1))
    raise SystemExit("gave up on " + url)


def parse_page(page_html):
    """Return (number of verses the page covers, commentary text with HTML removed).

    The verse count is taken from the verse links on the page; the text is the inner Arabic of
    every commentary block, tags stripped, entities unescaped, bidirectional controls dropped,
    non-breaking spaces written as spaces, blank lines collapsed.
    """
    verse_count = len(re.findall(VERSE_LINK_PATTERN, page_html))
    text_blocks = re.findall(COMMENTARY_TEXT_PATTERN, page_html, re.S)
    text = "\n".join(html.unescape(re.sub(r"<[^>]+>", "", block)).strip() for block in text_blocks)
    text = BIDI_CONTROLS.sub("", text).replace(NON_BREAKING_SPACE, " ")
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return verse_count, text


def resume_point(existing_text):
    """Return (text to keep, sura, verse) at which an interrupted download of this text continues.

    The last "=== sura:first-last ===" marker names the last passage saved. When the text ends
    with the passage terminator that passage is complete and the download goes on at the verse
    after it (or at verse 1 of the next sura when it ended the sura); otherwise the write was
    cut short inside that passage, so the text is kept only up to its marker and the passage is
    fetched again. A file without any marker is started from sura 78, verse 1, keeping its
    header.
    """
    markers = list(PASSAGE_MARKER_PATTERN.finditer(existing_text))
    if not markers:
        return existing_text, FIRST_SURA, 1
    last = markers[-1]
    sura, last_verse = int(last.group(1)), int(last.group(3))
    if not existing_text.endswith(PASSAGE_TERMINATOR):
        return existing_text[:last.start()], sura, int(last.group(2))
    if last_verse >= VERSES_PER_SURA[sura]:
        return existing_text, sura + 1, 1
    return existing_text, sura, last_verse + 1


def file_header(title, tafsir_no, download_date):
    """Return the two-line header of a commentary file; download_date None leaves the date out."""
    if download_date is None:
        return HEADER_WITHOUT_DATE.format(title=title, tafsir_no=tafsir_no)
    return HEADER_WITH_DATE.format(title=title, tafsir_no=tafsir_no, date=download_date)


def download_commentary(log_file, slug, download_date):
    """Download one commentary, sura by sura, into sources/altafsir-com/<slug>.txt.

    A file that already reaches sura 114 is left as it is; a file cut short by an earlier run
    is continued in append mode from the passage after its last complete one (resume_point).
    Each passage is written under a "=== sura:first-last ===" marker; the file is flushed after
    every passage so that an interrupted run leaves readable text. download_date (a string, or
    None for no date) goes into the header of a new file. A page without commentary text
    raises EmptyPage before anything is written for it; a file this call created and had not
    yet written a passage to is removed first, so an empty commentary leaves no file behind.
    """
    tafsir_no, title = TAFSIRS[slug]
    output_path = os.path.join(OUTPUT_FOLDER, slug + ".txt")
    start_sura, start_verse = FIRST_SURA, 1
    file_is_new = not os.path.exists(output_path)
    if not file_is_new:
        with open(output_path, encoding="utf8") as existing_file:
            existing_text = existing_file.read()
        if COMPLETE_FILE_MARKER in existing_text:
            log_message(log_file, f"{slug}: already complete")
            return
        kept_text, start_sura, start_verse = resume_point(existing_text)
        if kept_text != existing_text:
            # The last passage was cut mid-write: drop it so that it is fetched again whole.
            with open(output_path, "w", encoding="utf8") as output_file:
                output_file.write(kept_text)
        log_message(log_file, f"{slug}: resuming at {start_sura}:{start_verse}")
    else:
        with open(output_path, "w", encoding="utf8") as output_file:
            output_file.write(file_header(title, tafsir_no, download_date))
    if start_sura > LAST_SURA:
        log_message(log_file, f"{slug}: already complete")
        return
    passages_written = 0
    try:
        with open(output_path, "a", encoding="utf8") as output_file:
            for sura in range(start_sura, LAST_SURA + 1):
                verse = start_verse if sura == start_sura else 1
                while verse <= VERSES_PER_SURA[sura]:
                    verse_count, text = parse_page(fetch_page(log_file, tafsir_no, sura, verse))
                    if not text:
                        # No commentary text on the page: give the slug up rather than write an empty passage.
                        raise EmptyPage(EMPTY_PAGE_WARNING.format(slug=slug, sura=sura, verse=verse))
                    if verse_count == 0:
                        # A page without verse links still belongs to this verse; advance by one so the loop ends.
                        verse_count = 1
                    last_verse = min(verse + verse_count - 1, VERSES_PER_SURA[sura])
                    output_file.write(f"=== {sura}:{verse}-{last_verse} ===\n{text}{PASSAGE_TERMINATOR}")
                    output_file.flush()
                    passages_written += 1
                    log_message(log_file, f"{slug} {sura}:{verse}-{last_verse} {len(text)} chars")
                    verse = last_verse + 1
                    time.sleep(SECONDS_BETWEEN_PAGES)
    except EmptyPage:
        if file_is_new and passages_written == 0:
            os.remove(output_path)  # leave no header-only file behind for a commentary without text
        raise
    log_message(log_file, f"{slug}: done -> {output_path}")


def parse_arguments():
    """Parse the slugs to download (default: DEFAULT_SLUGS) and the header-date options."""
    parser = argparse.ArgumentParser(description="Download Ibadi commentaries on Juz' Amma from altafsir.com as text.")
    parser.add_argument("slugs", nargs="*", choices=list(TAFSIRS), metavar="slug",
                        help="commentary to download; default: " + ", ".join(DEFAULT_SLUGS)
                             + " (atfayyish-taysir-al-tafsir has no text on altafsir.com)")
    date_options = parser.add_mutually_exclusive_group()
    date_options.add_argument("--download-date", metavar="YYYY-MM-DD", default=None,
                              help="date written in the file header (default: today)")
    date_options.add_argument("--no-timestamp", action="store_true",
                              help="write the file header without the ', downloaded <date>' part")
    arguments = parser.parse_args()
    if arguments.download_date is not None:
        try:
            time.strptime(arguments.download_date, DATE_FORMAT)
        except ValueError:
            parser.error("--download-date must be YYYY-MM-DD, got " + arguments.download_date)
    return arguments


def main():
    """Parse the command line, download each requested commentary in turn, and exit non-zero if any was abandoned.

    A commentary whose page has no text (EmptyPage) is logged as a warning and skipped; the
    others are still downloaded. When at least one was abandoned the script ends with exit
    code EXIT_CODE_SLUG_ABANDONED and the abandoned slugs named on stderr.
    """
    arguments = parse_arguments()
    if arguments.no_timestamp:
        download_date = None
    else:
        download_date = arguments.download_date or time.strftime(DATE_FORMAT)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    abandoned = []
    with open(LOG_PATH, "a", encoding="utf8") as log_file:
        for slug in arguments.slugs or DEFAULT_SLUGS:
            try:
                download_commentary(log_file, slug, download_date)
            except EmptyPage as warning:
                log_message(log_file, "WARNING " + str(warning))
                abandoned.append(slug)
    if abandoned:
        print("abandoned (no text on the site): " + ", ".join(abandoned), file=sys.stderr)
        raise SystemExit(EXIT_CODE_SLUG_ABANDONED)


if __name__ == "__main__":
    main()
