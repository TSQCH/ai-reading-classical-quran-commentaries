"""Build the Springer LNCS reference document that pandoc uses for the SNM05 paper.

Paper: "AI-powered reading of Qur'an commentaries" (SNM05, Nizwa conference, 15 Nov 2026).
Written 4 Nov 2026 for draft v02; used by build_snm05_paper_docx_and_pdf.py for every version.

What it does
    Takes pandoc's default reference.docx and sets its styles to the Springer LNCS proceedings
    layout: A4 with a text area of 12.2 x 19.3 cm, Times New Roman 10 pt justified body, title
    14 pt bold centred, headings 12/10/10 pt bold, abstract and references 9 pt, captions 9 pt
    centred, code 8 pt Courier New. Theme-font attributes are stripped from every style so that
    Word cannot substitute its theme font for Times New Roman.

    Why: the template downloaded from the conference site (splnproc2510.docm, ianoman.org)
    could not be opened as a zip archive, so the LNCS geometry was rebuilt from the published
    specification.

What it reads
    pandoc's built-in default reference document (printed by pandoc itself).

What it writes
    In sources/springer-template/ (or in --output-dir):
    - pandoc-default-reference.docx, the untouched pandoc default, kept for comparison;
    - springer-lncs-reference-for-pandoc.docx, the styled reference document.

How to run it
    python -I scripts/build_springer_lncs_reference_docx_for_pandoc.py
    python -I scripts/build_springer_lncs_reference_docx_for_pandoc.py --output-dir <folder>
    Needs pypandoc_binary (bundles pandoc) and python-docx in the system site-packages.
"""

import argparse
import os
import subprocess

import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

# ---- paths ------------------------------------------------------------------------------------
PAPER_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT_FOLDER = os.path.join(PAPER_FOLDER, "sources", "springer-template")
PANDOC_DEFAULT_NAME = "pandoc-default-reference.docx"
OUTPUT_NAME = "springer-lncs-reference-for-pandoc.docx"

# ---- LNCS layout ------------------------------------------------------------------------------
BODY_FONT = "Times New Roman"
CODE_FONT = "Courier New"
JUSTIFY, CENTRE, LEFT = WD_ALIGN_PARAGRAPH.JUSTIFY, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT
# A4 page; the LNCS text area of 12.2 x 19.3 cm is obtained from these margins.
PAGE_WIDTH_CM, PAGE_HEIGHT_CM = 21.0, 29.7
SIDE_MARGIN_CM = 4.4
TOP_BOTTOM_MARGIN_CM = 5.2
HEADER_FOOTER_DISTANCE_CM = 3.9
# Theme-font attributes that would override the explicit font name in Word.
THEME_FONT_ATTRIBUTES = ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme")

# Style settings: (style name, keyword arguments for set_style). Styles pandoc does not define
# are skipped. Sizes in pt, spacing in pt, indent in cm.
STYLE_SETTINGS = [
    ("Normal", dict(size=10, align=JUSTIFY, before=0, after=0)),
    ("Body Text", dict(size=10, align=JUSTIFY, before=0, after=0, indent=0.5)),
    ("First Paragraph", dict(size=10, align=JUSTIFY, before=0, after=0, indent=0)),
    ("Title", dict(size=14, bold=True, align=CENTRE, before=0, after=12)),
    ("Subtitle", dict(size=10, bold=False, align=CENTRE, before=0, after=6)),
    ("Author", dict(size=10, bold=False, align=CENTRE, before=0, after=2)),
    ("Date", dict(size=9, align=CENTRE, before=0, after=12)),
    ("Abstract", dict(size=9, align=JUSTIFY, before=12, after=0)),
    ("Abstract Title", dict(size=9, bold=True, align=LEFT, before=12, after=0)),
    ("Heading 1", dict(size=12, bold=True, italic=False, align=LEFT, before=18, after=8)),
    ("Heading 2", dict(size=10, bold=True, italic=False, align=LEFT, before=12, after=6)),
    ("Heading 3", dict(size=10, bold=True, italic=True, align=LEFT, before=10, after=4)),
    ("Heading 4", dict(size=10, bold=False, italic=True, align=LEFT, before=8, after=4)),
    ("Block Text", dict(size=9, align=JUSTIFY, before=6, after=6)),
    ("Bibliography", dict(size=9, align=JUSTIFY, before=0, after=2, indent=0)),
    ("Compact", dict(size=10, align=JUSTIFY, before=0, after=0)),
    ("Table Caption", dict(size=9, align=CENTRE, before=6, after=4)),
    ("Image Caption", dict(size=9, align=CENTRE, before=4, after=10)),
    ("Footnote Text", dict(size=8, align=JUSTIFY, before=0, after=0)),
    ("Source Code", dict(size=8, font=CODE_FONT, before=4, after=4)),
    ("Verbatim Char", dict(size=8, font=CODE_FONT)),
]


def parse_arguments():
    """Return the parsed command line: only --output-dir, defaulting to sources/springer-template."""
    parser = argparse.ArgumentParser(description="Build the Springer LNCS reference docx for pandoc.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_FOLDER,
                        help="folder in which to write the two .docx files (default: sources/springer-template)")
    return parser.parse_args()


def write_pandoc_default_reference(path):
    """Ask pandoc to print its built-in reference.docx to the given path."""
    subprocess.run([pypandoc.get_pandoc_path(), "-o", path, "--print-default-data-file", "reference.docx"], check=True)


def set_style(document, name, size=None, bold=None, italic=None, align=None, before=None, after=None, font=BODY_FONT, indent=None):
    """Set font and paragraph format of one style; skip styles the document does not have.

    Only the arguments given are changed. The colour is reset so that pandoc's blue headings
    become black. Character styles have no paragraph format, so the paragraph settings are
    skipped for them.
    """
    try:
        style = document.styles[name]
    except KeyError:
        return
    style.font.name = font
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic
    style.font.color.rgb = None
    if not hasattr(style, "paragraph_format"):
        return
    paragraph_format = style.paragraph_format
    if align is not None:
        paragraph_format.alignment = align
    if before is not None:
        paragraph_format.space_before = Pt(before)
    if after is not None:
        paragraph_format.space_after = Pt(after)
    if indent is not None:
        paragraph_format.first_line_indent = Cm(indent)


def set_page_layout(document):
    """Set every section to A4 with the LNCS margins."""
    for section in document.sections:
        section.page_width, section.page_height = Cm(PAGE_WIDTH_CM), Cm(PAGE_HEIGHT_CM)
        section.left_margin = section.right_margin = Cm(SIDE_MARGIN_CM)
        section.top_margin, section.bottom_margin = Cm(TOP_BOTTOM_MARGIN_CM), Cm(TOP_BOTTOM_MARGIN_CM)
        section.header_distance, section.footer_distance = Cm(HEADER_FOOTER_DISTANCE_CM), Cm(HEADER_FOOTER_DISTANCE_CM)


def strip_theme_fonts(document):
    """Remove theme-font attributes from every style and from the document defaults.

    A theme attribute (asciiTheme etc.) takes precedence over the explicit font name, so the
    title and headings would come out in the theme font instead of Times New Roman.
    """
    for style in document.styles:
        run_properties = style.element.find(qn("w:rPr"))
        run_fonts = run_properties.find(qn("w:rFonts")) if run_properties is not None else None
        if run_fonts is not None:
            for attribute in THEME_FONT_ATTRIBUTES:
                if run_fonts.get(qn(attribute)) is not None:
                    del run_fonts.attrib[qn(attribute)]
            run_fonts.set(qn("w:ascii"), run_fonts.get(qn("w:ascii")) or BODY_FONT)
            run_fonts.set(qn("w:hAnsi"), run_fonts.get(qn("w:hAnsi")) or BODY_FONT)
    document_defaults = document.styles.element.find(qn("w:docDefaults"))
    if document_defaults is not None:
        for run_fonts in document_defaults.iter(qn("w:rFonts")):
            for attribute in THEME_FONT_ATTRIBUTES:
                if run_fonts.get(qn(attribute)) is not None:
                    del run_fonts.attrib[qn(attribute)]
            run_fonts.set(qn("w:ascii"), BODY_FONT)
            run_fonts.set(qn("w:hAnsi"), BODY_FONT)


def main():
    """Write pandoc's default reference, restyle it to LNCS, save the result."""
    arguments = parse_arguments()
    # The default folder is in .gitignore, so it does not exist in a fresh clone of the deposit.
    os.makedirs(arguments.output_dir, exist_ok=True)
    pandoc_default_path = os.path.join(arguments.output_dir, PANDOC_DEFAULT_NAME)
    output_path = os.path.join(arguments.output_dir, OUTPUT_NAME)
    write_pandoc_default_reference(pandoc_default_path)
    document = Document(pandoc_default_path)
    for style_name, settings in STYLE_SETTINGS:
        set_style(document, style_name, **settings)
    set_page_layout(document)
    strip_theme_fonts(document)
    document.save(output_path)
    print("written", output_path)


if __name__ == "__main__":
    main()
