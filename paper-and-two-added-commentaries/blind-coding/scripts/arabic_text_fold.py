"""Orthographic fold for checking that an Arabic quotation occurs in the text it was cut from.

Purpose
    A blind coder's quotation must occur in the text window it was served. Models often
    re-spell what they copy (a hamza dropped, a final ya written as alif maqsura, a comma
    added), so a strict substring test would reject quotations that are the same words. This
    module defines the one fold that every check applies, so that the run-time check of the
    runners and the after-the-fact check of the verifier accept exactly the same quotations.

    The fold forgives differences of spelling and punctuation, never of wording. It first
    applies Unicode compatibility normalisation (NFKC), so that a presentation-form ligature
    or a composed letter is spelt like its plain letters; then removes the Arabic combining
    marks (U+0610 to U+061A: the honorific signs and the small high marks; U+064B to U+065F:
    the vowel marks, shadda, sukun and the less common marks such as the small low seen and
    the wavy hamza; U+0670: the superscript alif; U+06D6 to U+06ED: the Qur'anic annotation
    marks, small high letters, end of ayah, sajdah and stop signs), the tatweel (U+0640) and
    the invisible bidirectional controls (U+200E, U+200F, U+061C, U+202A to U+202E, U+2066 to
    U+2069); turns punctuation into spaces; unifies the hamza and alif forms
    (hamza above or below, madda, wasla all become bare alif; hamza on waw becomes waw, hamza
    on ya becomes ya), the final ya (alif maqsura becomes ya) and the ta marbuta (becomes ha);
    and collapses runs of whitespace to one space.

Two identical copies
    paper-and-two-added-commentaries/blind-coding/scripts/arabic_text_fold.py
    first-twelve-commentaries/second-coding-by-external-AI/scripts/arabic_text_fold.py
    They are kept byte-identical: a change to one is a change to both. The Ollama runner and
    the Gemini CLI runner of each folder, and the DeepSeek API runner of the first-set folder,
    import the copy beside them (the archived API runner makes no content check); the verifier
    paper-and-two-added-commentaries/scripts/verify_blind_coders_quotations_against_windows.py
    imports the Oman copy. Every importer adds its own folder to sys.path first, because
    `python -I` (the documented way to run the scripts) does not put the script folder there.

Reads and writes
    Nothing: pure functions on strings.

Use
    from arabic_text_fold import collapse, fold, quotation_occurs
    quotation_occurs(quote, window) is True when the quote occurs in the window as written
    (whitespace collapsed) or after the fold is applied to both.
"""

import re
import unicodedata

UNICODE_NORMALISATION_FORM = "NFKC"  # compatibility decomposition then canonical composition, applied before the fold
# The Arabic combining marks (U+0610-U+061A, U+064B-U+065F, U+0670, U+06D6-U+06ED), the tatweel (U+0640)
# and the invisible bidirectional controls (U+200E, U+200F, U+061C, U+202A-U+202E, U+2066-U+2069).
VOWEL_MARKS_AND_TATWEEL = re.compile(  # written as \u escapes because the marks and controls are invisible or combining
    "[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u200E\u200F\u061C\u202A-\u202E\u2066-\u2069]")
# Whitespace and the punctuation a model may add or drop around a quotation (Arabic and Latin
# commas, semicolons, colons, quotation marks, brackets, ellipsis, dashes).
PUNCTUATION_AND_SPACE = re.compile(r"[\s\.,،؛:;\"'«»\(\)\[\]\{\}…\-–—]+")
WHITESPACE = re.compile(r"\s+")
# Hamza and alif forms unified to bare alif.
ALIF_FORMS = re.compile("[أإآٱ]")
# Letter-for-letter unifications: alif maqsura to ya, ta marbuta to ha, hamza on waw to waw, hamza on ya to ya.
LETTER_FOLDS = (("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي"))


def collapse(text):
    """Collapse runs of whitespace to one space and strip the ends."""
    return WHITESPACE.sub(" ", text).strip()


def fold(text):
    """Orthographic fold: NFKC; remove combining marks, tatweel, bidirectional controls and punctuation; unify hamza/alif, final ya, ta marbuta."""
    text = unicodedata.normalize(UNICODE_NORMALISATION_FORM, text)
    text = VOWEL_MARKS_AND_TATWEEL.sub("", text)
    text = PUNCTUATION_AND_SPACE.sub(" ", text)
    text = ALIF_FORMS.sub("ا", text)
    for letter, replacement in LETTER_FOLDS:
        text = text.replace(letter, replacement)
    return collapse(text)


def quotation_occurs(quote, window):
    """Return True when the quote occurs in the window as written (whitespace collapsed) or after the fold.

    An empty quote, or one that the fold reduces to nothing (vowel marks or punctuation only),
    occurs nowhere: without this test Python would find the empty string in every window.
    """
    if not fold(quote):
        return False
    return collapse(quote) in collapse(window) or fold(quote) in fold(window)
