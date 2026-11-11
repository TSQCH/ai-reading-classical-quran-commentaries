"""Build the SNM05 paper as .docx and .pdf from a Markdown draft.

Paper: "AI-powered reading of Qur'an commentaries" (SNM05, Nizwa conference, 15 Nov 2026).
Written 4 Nov 2026 for draft v03 and used for every later version, with the changes below.
5 Nov 2026: a time limit on the Word export (WORD_EXPORT_TIMEOUT_SECONDS).
5 Nov 2026, for the submission build of v18: column widths chosen per table so that no header
or cell breaks inside a word (the nine-column quotation table is set in 8 pt with its own
widths), narrow cell margins, the author and affiliation lines centred, and the code block and
the reference list set flush left so that a long address does not stretch a justified line.
6 Nov 2026: a figure that has a vector copy (.svg) beside its .png gets that copy embedded
behind the picture, because Word reduces a 300 dpi picture to about 200 dpi in the PDF and
none of its settings prevents that; a vector copy is exported as line art, at any resolution.
6 Nov 2026: each table is kept on one page with its caption (the header rows of Tables 1 and
4 had been left at the foot of a page, with the rest of the table on the next), and the
paragraph that follows a table starts SPACE_AFTER_TABLE_PT below its bottom rule.
6 Nov 2026, after the sixth code review: a missing package is reported with the command that
installs it, and on Linux or macOS, where Word cannot be automated, the build writes the
.docx and says that the .pdf was not built instead of failing.

What it does
    1. Converts the Markdown draft to .docx with pandoc, using the Springer LNCS reference
       document (built by build_springer_lncs_reference_docx_for_pandoc.py if it is missing).
    2. Fixes the tables, which pandoc would otherwise set with the body indent and
       justification inherited into the cells: cells left-aligned without indent, 9 pt, the
       first column wide and the rest sharing the remaining width (COLUMN_WIDTHS_CM gives
       explicit widths for the nine-column table), with a thin rule above and below each table.
       Every table is kept on one page together with its caption, so that no header row is
       left alone at the foot of a page and repeated on the next, and the paragraph after
       a table is set a little below it.
    2b. Centres the author and affiliation lines, and sets the code block and the reference
       list flush left.
    2c. For every picture whose .png has an .svg of the same name beside it, embeds the .svg
       in the .docx as the picture's vector form (Word 2016 and later show and export the
       vector form; older versions fall back to the .png).
    3. Exports the .docx to .pdf through Microsoft Word (COM automation) and prints the page
       count, which is what the LNCS page limit is checked against. The export is given
       WORD_EXPORT_TIMEOUT_SECONDS (300 s); if Word has not finished by then (a dialog, a
       locked file) the build stops with an error that says so.

What it reads
    - The Markdown draft given as the first argument (images such as
      figures/SNM05-figure-1-...png are resolved relative to the current working directory,
      so run it from the paper folder).
    - sources/springer-template/springer-lncs-reference-for-pandoc.docx.

What it writes
    The .docx and .pdf next to the draft, with the same base name.

How to run it
    python -I scripts/build_snm05_paper_docx_and_pdf.py <draft .md>
    (python -I scripts/build_snm05_paper_docx_and_pdf.py --help lists the arguments.)
    Needs pypandoc_binary (bundles pandoc) and python-docx in the system site-packages, and
    Microsoft Word on Windows for the PDF. On Linux or macOS the .docx is built and the PDF
    step is skipped with a message; open the .docx in Word or LibreOffice and export it there
    (the page breaks may then differ from the authors' PDF). The reference document, when it has to be built, is built in
    a child Python run without -I, so that packages in the user site-packages are visible to it.
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile

INSTALL_HINT = ("This build needs the packages pypandoc_binary (which bundles pandoc) and python-docx.\n"
                "Install them with:  python -m pip install pypandoc_binary python-docx")

try:
    import pypandoc
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
    from docx.text.paragraph import Paragraph
except ImportError as missing_package:
    raise SystemExit(f"{missing_package}\n{INSTALL_HINT}")

# ---- paths ------------------------------------------------------------------------------------
PAPER_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE_DOCX = os.path.join(PAPER_FOLDER, "sources", "springer-template", "springer-lncs-reference-for-pandoc.docx")
REFERENCE_BUILDER_SCRIPT = os.path.join(PAPER_FOLDER, "scripts", "build_springer_lncs_reference_docx_for_pandoc.py")

# ---- pandoc -----------------------------------------------------------------------------------
# "+smart" turns straight quotes and dashes into typographic ones, as the LNCS template expects.
PANDOC_INPUT_FORMAT = "markdown+smart"

# ---- table layout (LNCS text width is 12.2 cm) ------------------------------------------------
TEXT_WIDTH_CM = 12.2
FIRST_COLUMN_SHARE = 0.34          # the first column of a narrow table; the other columns share the rest
# Tables of seven columns (Tables 1 and 2): a narrower first column, so that "0.89 (93)" and
# "Sec./pos." each stay on one line in the other six.
FIRST_COLUMN_SHARE_BY_COLUMN_COUNT = {7: 0.30}
# The nine-column quotation table (Table 4): model, then for each of the two sets the columns
# quotations, verbatim, elided, not found. The widths sum to the text width.
COLUMN_WIDTHS_CM = {9: [2.4, 1.45, 1.55, 0.95, 0.95, 1.45, 1.55, 0.95, 0.95]}
TABLE_FONT_SIZE_PT = 9
TABLE_FONT_SIZE_PT_BY_COLUMN_COUNT = {9: 8}   # the nine-column table needs the smaller size to fit
CELL_SIDE_MARGIN_TWIPS = "40"      # left and right cell margin, 0.07 cm (Word's default is 0.19 cm)

# ---- paragraphs outside the tables ------------------------------------------------------------
CODE_BLOCK_STYLE = "Source Code"   # pandoc's style for a fenced code block
ABSTRACT_OPENING = "Abstract."     # the first words of the abstract paragraph
REFERENCES_HEADING = "References"
TITLE_STYLE = "Title"
CELL_SPACE_BEFORE_PT = 1
CELL_SPACE_AFTER_PT = 1
TABLE_RULE_SIDES = ("top", "bottom")
TABLE_RULE_WIDTH_EIGHTHS_PT = "6"  # Word measures border width in eighths of a point: 0.75 pt
TABLE_RULE_COLOUR = "000000"
SPACE_AFTER_TABLE_PT = 6           # gap between a table's bottom rule and the text that follows
HEADING_STYLE_PREFIX = "Heading"   # a heading after a table keeps the larger space of its own style

# ---- vector copies of the figures -------------------------------------------------------------
DOCUMENT_PART = "word/document.xml"
RELATIONSHIPS_PART = "word/_rels/document.xml.rels"
CONTENT_TYPES_PART = "[Content_Types].xml"
SVG_CONTENT_TYPE_DEFAULT = '<Default Extension="svg" ContentType="image/svg+xml"/>'
IMAGE_RELATIONSHIP_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
# Office's extension that attaches an SVG to a picture; the identifier is fixed by Microsoft.
SVG_EXTENSION_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NAMESPACE = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
PICTURE_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/picture"
DRAWING_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/main"

# ---- Word PDF export --------------------------------------------------------------------------
WINDOWS_OS_NAME = "nt"             # os.name on Windows, the only system on which Word can be automated
PDF_SKIPPED_MESSAGE = ("pdf: not built. The PDF is exported through Microsoft Word, which this script can drive "
                       "only on Windows. Open the .docx in Word or LibreOffice and export it as PDF.")
WORD_EXPORT_FORMAT_PDF = 17        # WdExportFormat.wdExportFormatPDF
WORD_STATISTIC_PAGES = 2           # WdStatistic.wdStatisticPages
WORD_CLOSE_WITHOUT_SAVING = 0      # WdSaveOptions.wdDoNotSaveChanges
STDERR_PREVIEW_CHARACTERS = 300
WORD_EXPORT_TIMEOUT_SECONDS = 300  # a Word stuck behind a dialog must not stall the build for ever


def ensure_reference_docx():
    """Build the LNCS reference document if it does not exist yet (without -I: user site-packages must be visible)."""
    if not os.path.exists(REFERENCE_DOCX):
        subprocess.run([sys.executable, REFERENCE_BUILDER_SCRIPT], check=True)


def convert_markdown_to_docx(markdown_path, docx_path):
    """Run pandoc on the draft with the LNCS reference document.

    Stops the build with the installation hint when pypandoc finds no pandoc program
    (the package pypandoc, unlike pypandoc_binary, does not bring one).
    """
    try:
        pypandoc.get_pandoc_version()
    except OSError as pandoc_missing:
        raise SystemExit(f"{pandoc_missing}\n{INSTALL_HINT}")
    pypandoc.convert_file(markdown_path, "docx", outputfile=docx_path,
                          extra_args=["--reference-doc=" + REFERENCE_DOCX, "--from=" + PANDOC_INPUT_FORMAT])


def column_widths(column_count):
    """Return the cell widths of a table with column_count columns.

    Explicit widths where COLUMN_WIDTHS_CM gives them; otherwise the first column takes its
    share of the text width and the others share the rest equally.
    """
    if column_count in COLUMN_WIDTHS_CM:
        return [Cm(width) for width in COLUMN_WIDTHS_CM[column_count]]
    first_share = FIRST_COLUMN_SHARE_BY_COLUMN_COUNT.get(column_count, FIRST_COLUMN_SHARE)
    first_width = Cm(TEXT_WIDTH_CM * first_share)
    other_width = Cm(TEXT_WIDTH_CM * (1 - first_share) / max(1, column_count - 1))
    return [first_width] + [other_width] * (column_count - 1)


def set_cell_side_margins(table):
    """Narrow the left and right margins of every cell of the table to CELL_SIDE_MARGIN_TWIPS."""
    table_properties = table._tbl.tblPr
    for old_margins in table_properties.findall(qn("w:tblCellMar")):
        table_properties.remove(old_margins)
    margins = OxmlElement("w:tblCellMar")
    for side in ("left", "right"):
        margin = OxmlElement(f"w:{side}")
        margin.set(qn("w:w"), CELL_SIDE_MARGIN_TWIPS)
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    table_properties.append(margins)


def format_cell_paragraphs(cell, font_size_pt):
    """Set every paragraph of a cell left-aligned, unindented, tight, in the given font size."""
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.space_after = Pt(CELL_SPACE_AFTER_PT)
        paragraph.paragraph_format.space_before = Pt(CELL_SPACE_BEFORE_PT)
        for run in paragraph.runs:
            run.font.size = Pt(font_size_pt)


def set_table_rules(table):
    """Replace the table's borders with a single thin rule above and below it."""
    table_properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in TABLE_RULE_SIDES:
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), TABLE_RULE_WIDTH_EIGHTHS_PT)
        border.set(qn("w:color"), TABLE_RULE_COLOUR)
        borders.append(border)
    for old_borders in table_properties.findall(qn("w:tblBorders")):
        table_properties.remove(old_borders)
    table_properties.append(borders)


def keep_table_on_one_page(table):
    """Keep the caption above a table, and all the table's rows, together on one page.

    Word keeps a paragraph on the page of the paragraph that follows it when "keep with next"
    is set; set on the caption and on every row but the last, it chains the caption and the
    rows together. A row is also forbidden to break inside itself.
    """
    caption = table._tbl.getprevious()
    if caption is not None and caption.tag == qn("w:p"):
        caption_properties = caption.get_or_add_pPr()
        caption_properties.append(OxmlElement("w:keepNext"))
        caption_properties.append(OxmlElement("w:keepLines"))
    for row in table.rows[:-1]:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next = True
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def set_space_after_table(table, document):
    """Start the paragraph that follows a table SPACE_AFTER_TABLE_PT below the table.

    A table has no "space after" of its own in Word, so the space is put before the next
    paragraph. A heading is left alone: its style already sets a larger space before it.
    """
    following = table._tbl.getnext()
    if following is None or following.tag != qn("w:p"):
        return
    paragraph = Paragraph(following, document)
    if not paragraph.style.name.startswith(HEADING_STYLE_PREFIX):
        paragraph.paragraph_format.space_before = Pt(SPACE_AFTER_TABLE_PT)


def fix_tables(docx_path):
    """Apply the LNCS table layout to every table in the document and save it in place."""
    document = Document(docx_path)
    for table in document.tables:
        column_count = len(table.columns)
        widths = column_widths(column_count)
        font_size_pt = TABLE_FONT_SIZE_PT_BY_COLUMN_COUNT.get(column_count, TABLE_FONT_SIZE_PT)
        table.autofit = False
        for row in table.rows:
            for column_index, cell in enumerate(row.cells):
                cell.width = widths[min(column_index, column_count - 1)]
                format_cell_paragraphs(cell, font_size_pt)
        set_cell_side_margins(table)
        set_table_rules(table)
        keep_table_on_one_page(table)
        set_space_after_table(table, document)
    fix_paragraphs(document)
    document.save(docx_path)


def set_flush(paragraph, alignment):
    """Give a paragraph the alignment and remove its first-line indent."""
    paragraph.alignment = alignment
    paragraph.paragraph_format.first_line_indent = Cm(0)


def fix_paragraphs(document):
    """Centre the author block; set the code block and the reference list flush left.

    The author block is every paragraph between the title and the abstract. The reference
    list is every paragraph after the "References" heading (the numbered references and the
    editions of the commentaries): flush left, because a justified line that ends in a long
    DOI address is stretched across the measure.
    """
    before_abstract, in_references = True, False
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text.startswith(ABSTRACT_OPENING):
            before_abstract = False
        if before_abstract and text and paragraph.style.name != TITLE_STYLE:
            set_flush(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
        elif paragraph.style.name == CODE_BLOCK_STYLE:
            set_flush(paragraph, WD_ALIGN_PARAGRAPH.LEFT)
        elif in_references and text:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if text == REFERENCES_HEADING:
            in_references = True


def vector_copies_by_picture(document):
    """Return {relationship id of the picture: path of its .svg} for pictures that have one.

    pandoc records the path of each image file in the picture's description; a picture
    qualifies when a file of the same name with the extension .svg lies beside that file.
    """
    vector_copies = {}
    for picture in document.element.body.iter("{%s}pic" % PICTURE_NAMESPACE):
        source_path = picture.find("{%s}nvPicPr/{%s}cNvPr" % (PICTURE_NAMESPACE, PICTURE_NAMESPACE)).get("descr", "")
        vector_path = os.path.splitext(source_path)[0] + ".svg"
        if source_path and os.path.exists(vector_path):
            blip = picture.find("{%s}blipFill/{%s}blip" % (PICTURE_NAMESPACE, DRAWING_NAMESPACE))
            vector_copies[blip.get(qn("r:embed"))] = vector_path
    return vector_copies


def with_vector_references(part_name, text, vector_copies):
    """Return the text of one part of the .docx with the vector copies referenced in it."""
    for picture_id, vector_path in vector_copies.items():
        vector_id = picture_id + "svg"
        if part_name == DOCUMENT_PART:
            plain_blip = f'<a:blip r:embed="{picture_id}"/>'
            if text.count(plain_blip) != 1:
                raise SystemExit(f"picture {picture_id}: expected one plain reference")
            text = text.replace(plain_blip, (
                f'<a:blip r:embed="{picture_id}"><a:extLst><a:ext uri="{SVG_EXTENSION_URI}">'
                f'<asvg:svgBlip xmlns:asvg="{SVG_NAMESPACE}" r:embed="{vector_id}"/>'
                f'</a:ext></a:extLst></a:blip>'))
        elif part_name == RELATIONSHIPS_PART:
            text = text.replace("</Relationships>", (
                f'<Relationship Id="{vector_id}" Type="{IMAGE_RELATIONSHIP_TYPE}" '
                f'Target="media/{os.path.basename(vector_path)}"/></Relationships>'))
    if part_name == CONTENT_TYPES_PART and SVG_CONTENT_TYPE_DEFAULT not in text:
        text = text.replace("<Default ", SVG_CONTENT_TYPE_DEFAULT + "<Default ", 1)
    return text


def embed_vector_figures(docx_path):
    """Embed the .svg of every picture that has one, in place; print what was embedded.

    The .docx is a zip archive. Three of its parts change: the document (the picture gains a
    reference to its vector form), the relationships (the reference is given a target) and
    the content types (the extension .svg is declared); the .svg files are added as media.
    """
    vector_copies = vector_copies_by_picture(Document(docx_path))
    if not vector_copies:
        return
    temporary_path = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path) as source, zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename in (DOCUMENT_PART, RELATIONSHIPS_PART, CONTENT_TYPES_PART):
                content = with_vector_references(item.filename, content.decode("utf8"), vector_copies).encode("utf8")
            target.writestr(item, content)
        for vector_path in vector_copies.values():
            target.write(vector_path, "word/media/" + os.path.basename(vector_path))
            print("vector figure embedded:", vector_path)
    shutil.move(temporary_path, docx_path)


def export_pdf_with_word(docx_path, pdf_path):
    """Open the .docx in Word, export it as PDF, and print Word's page count; stop if no PDF results.

    A PDF left by an earlier build is removed first, so that it cannot pass for the new one.

    Stops the build (SystemExit) when Word has not finished within WORD_EXPORT_TIMEOUT_SECONDS.
    """
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    powershell_script = f'''
$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0
$d = $w.Documents.Open("{docx_path}"); $d.ExportAsFixedFormat("{pdf_path}", {WORD_EXPORT_FORMAT_PDF}); $pages = $d.ComputeStatistics({WORD_STATISTIC_PAGES}); $d.Close({WORD_CLOSE_WITHOUT_SAVING}); $w.Quit()
"pages: $pages"
'''
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
                                capture_output=True, text=True, timeout=WORD_EXPORT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"Word did not finish exporting {docx_path} to PDF within {WORD_EXPORT_TIMEOUT_SECONDS} s. "
                         "Close any Word dialog or Word instance still open (Task Manager: WINWORD.EXE) and run the build again.")
    print(result.stdout.strip(), result.stderr.strip()[:STDERR_PREVIEW_CHARACTERS])
    if result.returncode != 0 or not os.path.exists(pdf_path):
        raise SystemExit(f"Word did not export {pdf_path}; see the message above.")


def parse_arguments():
    """Return the parsed command line: the Markdown draft to build."""
    parser = argparse.ArgumentParser(description="Build the SNM05 paper as .docx and .pdf from a Markdown draft.")
    parser.add_argument("draft", help="the Markdown draft (.md); the .docx and .pdf are written next to it")
    return parser.parse_args()


def main():
    """Build the .docx and the .pdf next to the draft named on the command line."""
    markdown_path = os.path.abspath(parse_arguments().draft)
    base_path = os.path.splitext(markdown_path)[0]
    docx_path = base_path + ".docx"
    pdf_path = base_path + ".pdf"
    ensure_reference_docx()
    convert_markdown_to_docx(markdown_path, docx_path)
    fix_tables(docx_path)
    embed_vector_figures(docx_path)
    print("docx:", docx_path)
    if os.name != WINDOWS_OS_NAME:
        print(PDF_SKIPPED_MESSAGE)
        return
    export_pdf_with_word(docx_path, pdf_path)
    print("pdf:", pdf_path)


if __name__ == "__main__":
    main()
