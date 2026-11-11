"""Draw Figure 1 of the SNM05 paper: the source-bound reading pipeline.

Paper: "AI-powered reading of Qur'an commentaries" (SNM05, Nizwa conference, 15 Nov 2026).
Version: drawn for draft v09, 4 Nov 2026; placed in Section 3.1 by make_snm05_paper_v09_from_v08.py.
6 Nov 2026: the same drawing is also saved as a vector file (SVG), because Word reduces a
300 dpi picture to about 200 dpi when it exports the PDF; the build script puts the vector
copy behind the picture, and Word exports that as line art. The PNG is unchanged.

What it does
    Draws five stages left to right, each as a hand-drawn icon with a title and a three-line
    caption, joined by arrows: (1) a commentary page, (2) the text window (a page with a
    highlighted band and a bracket), (3) the model (a cloud for the service models above a
    graphics card for the local models), (4) a verification shield with a tick, and (5) the
    output table with one highlighted cell. The figure is sized for the LNCS text width,
    122 mm by 34 mm, at 300 dpi.

What it reads
    Nothing.

What it writes
    figures/SNM05-figure-1-source-bound-reading-pipeline.png in the paper folder (or in
    --output-dir), on a white background, and the same drawing as .svg beside it.

How to run it
    python scripts/snm05-v09/draw_snm05_figure_1_source_bound_pipeline.py
    python scripts/snm05-v09/draw_snm05_figure_1_source_bound_pipeline.py --output-dir <folder>
    python -I works when matplotlib was installed as the README says; use plain "python" if it
    sits in the user site-packages, which -I hides. The output is deterministic (no timestamp), so a re-run reproduces the PNG
    byte for byte; the SVG likewise (fixed identifiers, no date, text drawn as outlines so
    that it does not depend on the fonts of the PC that opens it).
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle, Circle, FancyArrowPatch

# ---- paths ------------------------------------------------------------------------------------
PAPER_FOLDER = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUTPUT_FOLDER = os.path.join(PAPER_FOLDER, "figures")
OUTPUT_FILE_NAME = "SNM05-figure-1-source-bound-reading-pipeline.png"
VECTOR_OUTPUT_FILE_NAME = "SNM05-figure-1-source-bound-reading-pipeline.svg"
# SVG settings: text as outlines, and a fixed salt so that the identifiers inside the file
# are the same on every run.
SVG_SETTINGS = {"svg.fonttype": "path", "svg.hashsalt": "SNM05-figure-1"}
SVG_METADATA = {"Date": None}   # no creation date in the file

# ---- colours ----------------------------------------------------------------------------------
NAVY = "#1F3A5F"    # outlines, titles, table header
TEAL = "#2A7F8E"    # arrows, verification shield
GOLD = "#C9A227"    # highlighted text band, bracket, highlighted table cell
MUTED = "#5B6B7B"   # captions, faint text lines, table rules
PALE = "#E8EEF4"    # folded page corner

# ---- geometry (figure units are millimetres: the axes span 0..WIDTH_MM by 0..HEIGHT_MM) --------
WIDTH_MM, HEIGHT_MM = 122, 34   # LNCS text width
DPI = 300
MM_PER_INCH = 25.4
FONT = dict(family=["Arial", "DejaVu Sans", "sans-serif"])  # a stack: Arial where installed (byte-identical PNG), else matplotlib's DejaVu Sans
STAGE_CENTRES_X = [12, 36, 61, 86, 110]   # x of the five stages
ICON_CENTRE_Y = 23                          # icons are centred around this y; captions sit below
CAPTION_TOP_Y = 12.5                        # top of the title line under each icon
ARROW_GAP_MM = 8.5                          # arrows start/end this far from a stage centre
TITLE_FONT_SIZE, CAPTION_FONT_SIZE, SMALL_LABEL_FONT_SIZE = 6.2, 4.4, 3.8
CAPTION_OFFSET_MM = 3.2                     # caption starts this far below the title

# Page icon: width, height, number of text lines, size of the folded corner.
PAGE_WIDTH, PAGE_HEIGHT, PAGE_LINES, PAGE_FOLD = 9, 13, 7, 2.2
# Lines of the text window that are highlighted (zero-based, from the top).
WINDOW_HIGHLIGHTED_LINES = {2, 3, 4}
# Cloud icon: (dx, dy, radius) of its five circles around the cloud centre.
CLOUD_CIRCLES = [(-2.4, 0.9, 1.9), (0, 1.9, 2.5), (2.5, 0.9, 1.9), (-1.0, -0.2, 2.0), (1.2, -0.2, 2.0)]
CLOUD_CENTRE_OFFSET_Y = 5.0                 # cloud centre above the icon centre
CLOUD_INNER_SHRINK = 0.4                    # inner white circles hide the overlapping outlines
# Graphics card icon: card box, chip, fan and five connector pins.
CARD_WIDTH, CARD_HEIGHT, CARD_PIN_COUNT, CARD_PIN_SPACING = 10, 5.2, 5, 2.0
# Output table icon: width, height, header height, rows and columns.
TABLE_WIDTH, TABLE_HEIGHT, TABLE_HEADER_HEIGHT, TABLE_DIVISIONS = 12, 11, 2.4, 4

# Captions of the five stages: (title, three-line description).
STAGE_CAPTIONS = [
    ("Commentary", "one disputed point,\none commentator\n(67 points, 14 works)"),
    ("Text window", "1,500 characters each side,\nvowel marks removed;\nrule + JSON schema"),
    ("Model", "nine open-weight models,\none position per call, temp. 0;\nClaude, Gemini: packets"),
    ("Verification", "schema, row, views in list,\nquotation verbatim in window;\nretry once, else flagged"),
    ("Output", "type, views held, quotation,\nvolume and page; flagged\nrows to a human reader"),
]


def parse_arguments():
    """Return the parsed command line: only --output-dir, defaulting to the figures folder."""
    parser = argparse.ArgumentParser(description="Draw Figure 1 of the SNM05 paper.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_FOLDER,
                        help="folder in which to write the PNG (default: the paper's figures folder)")
    return parser.parse_args()


def draw_caption(axes, centre_x, top_y, title, description):
    """Write a bold title and a muted three-line description under an icon."""
    axes.text(centre_x, top_y, title, ha="center", va="top", fontsize=TITLE_FONT_SIZE, fontweight="bold", color=NAVY, **FONT)
    axes.text(centre_x, top_y - CAPTION_OFFSET_MM, description, ha="center", va="top", fontsize=CAPTION_FONT_SIZE, color=MUTED, linespacing=1.3, **FONT)


def draw_page(axes, left_x, top_y, width, height, lines=6, fold=2.2, highlighted_lines=None):
    """Draw a page icon with a folded corner and `lines` text lines.

    highlighted_lines: set of line indexes drawn in navy on a gold band; the other lines are
    muted. None draws every line in navy without a band (the plain commentary page).
    """
    outline = [(left_x, top_y), (left_x + width - fold, top_y), (left_x + width, top_y - fold), (left_x + width, top_y - height), (left_x, top_y - height)]
    axes.add_patch(Polygon(outline, closed=True, facecolor="white", edgecolor=NAVY, linewidth=0.7))
    corner = [(left_x + width - fold, top_y), (left_x + width - fold, top_y - fold), (left_x + width, top_y - fold)]
    axes.add_patch(Polygon(corner, closed=True, facecolor=PALE, edgecolor=NAVY, linewidth=0.5))
    for line_index in range(lines):
        line_y = top_y - 3.2 - line_index * (height - 4.4) / (lines - 1)
        is_highlighted = highlighted_lines is not None and line_index in highlighted_lines
        if is_highlighted:
            axes.add_patch(Rectangle((left_x + 1.3, line_y - 0.55), width - 2.6, 1.1, facecolor=GOLD, alpha=0.55, linewidth=0))
        # Every third line is drawn shorter, as a paragraph end would look; lines are drawn from
        # the right edge, as Arabic text runs.
        line_end_x = left_x + 1.6 + (0.9 if line_index % 3 == 2 else 0)
        line_colour = NAVY if highlighted_lines is None or is_highlighted else MUTED
        axes.plot([left_x + width - 1.6, line_end_x], [line_y, line_y], color=line_colour, linewidth=0.55, solid_capstyle="round")


def draw_arrow(axes, start_x, end_x, y):
    """Draw a teal arrow from start_x to end_x at height y."""
    axes.add_patch(FancyArrowPatch((start_x, y), (end_x, y), arrowstyle="-|>", mutation_scale=7, linewidth=0.8, color=TEAL))


def draw_commentary_page(axes, centre_x):
    """Stage 1: a plain commentary page."""
    draw_page(axes, centre_x - 4.5, ICON_CENTRE_Y + 6.5, PAGE_WIDTH, PAGE_HEIGHT, lines=PAGE_LINES, fold=PAGE_FOLD)


def draw_text_window(axes, centre_x):
    """Stage 2: a page with three highlighted lines and a gold bracket to their left."""
    draw_page(axes, centre_x - 4.5, ICON_CENTRE_Y + 6.5, PAGE_WIDTH, PAGE_HEIGHT, lines=PAGE_LINES, fold=PAGE_FOLD, highlighted_lines=WINDOW_HIGHLIGHTED_LINES)
    bracket_x = [centre_x - 6.5, centre_x - 7.3, centre_x - 7.3, centre_x - 6.5]
    bracket_y = [ICON_CENTRE_Y + 2.9, ICON_CENTRE_Y + 2.9, ICON_CENTRE_Y - 3.1, ICON_CENTRE_Y - 3.1]
    axes.plot(bracket_x, bracket_y, color=GOLD, linewidth=0.8)


def draw_model(axes, centre_x):
    """Stage 3: a cloud (service models) above a graphics card (local, four-bit models)."""
    cloud_centre_y = ICON_CENTRE_Y + CLOUD_CENTRE_OFFSET_Y
    for offset_x, offset_y, radius in CLOUD_CIRCLES:
        axes.add_patch(Circle((centre_x + offset_x, cloud_centre_y + offset_y), radius, facecolor="white", edgecolor=NAVY, linewidth=0.7))
    # A second pass of slightly smaller white circles covers the outlines inside the cloud, so
    # that only the outer silhouette stays visible.
    for offset_x, offset_y, radius in CLOUD_CIRCLES:
        axes.add_patch(Circle((centre_x + offset_x, cloud_centre_y + offset_y), radius - CLOUD_INNER_SHRINK, facecolor="white", edgecolor="none"))
    axes.text(centre_x, ICON_CENTRE_Y + 2.2, "service", ha="center", va="top", fontsize=SMALL_LABEL_FONT_SIZE, color=NAVY, **FONT)
    # Graphics card: rounded box, a navy chip, a round fan and five pins along the bottom edge.
    axes.add_patch(FancyBboxPatch((centre_x - 5, ICON_CENTRE_Y - 4.6), CARD_WIDTH, CARD_HEIGHT, boxstyle="round,pad=0,rounding_size=0.6", facecolor="white", edgecolor=NAVY, linewidth=0.7))
    axes.add_patch(Rectangle((centre_x - 3.2, ICON_CENTRE_Y - 3.4), 3.2, 2.8, facecolor=NAVY, edgecolor="none"))
    axes.add_patch(Circle((centre_x + 2.2, ICON_CENTRE_Y - 2.0), 1.3, facecolor="white", edgecolor=NAVY, linewidth=0.6))
    for pin_index in range(CARD_PIN_COUNT):
        pin_x = centre_x - 4.2 + pin_index * CARD_PIN_SPACING
        axes.plot([pin_x, pin_x], [ICON_CENTRE_Y - 4.6, ICON_CENTRE_Y - 5.6], color=NAVY, linewidth=0.6)
    axes.text(centre_x, ICON_CENTRE_Y - 6.6, "local, 4-bit", ha="center", va="top", fontsize=SMALL_LABEL_FONT_SIZE, color=NAVY, **FONT)


def draw_verification_shield(axes, centre_x):
    """Stage 4: a teal shield with a white tick."""
    shield = [(centre_x - 5, ICON_CENTRE_Y + 5.5), (centre_x + 5, ICON_CENTRE_Y + 5.5), (centre_x + 5, ICON_CENTRE_Y - 0.5), (centre_x, ICON_CENTRE_Y - 5.5), (centre_x - 5, ICON_CENTRE_Y - 0.5)]
    axes.add_patch(Polygon(shield, closed=True, facecolor=TEAL, edgecolor="none"))
    axes.plot([centre_x - 2.4, centre_x - 0.6, centre_x + 2.8], [ICON_CENTRE_Y + 0.4, ICON_CENTRE_Y - 1.6, ICON_CENTRE_Y + 2.6], color="white", linewidth=1.4, solid_capstyle="round", solid_joinstyle="round")


def draw_output_table(axes, centre_x):
    """Stage 5: a table with a navy header, a 4 x 4 grid and one gold cell."""
    left_x, top_y = centre_x - 6, ICON_CENTRE_Y + 5.5
    axes.add_patch(Rectangle((left_x, top_y - TABLE_HEIGHT), TABLE_WIDTH, TABLE_HEIGHT, facecolor="white", edgecolor=NAVY, linewidth=0.7))
    axes.add_patch(Rectangle((left_x, top_y - TABLE_HEADER_HEIGHT), TABLE_WIDTH, TABLE_HEADER_HEIGHT, facecolor=NAVY, edgecolor="none"))
    row_height = (TABLE_HEIGHT - TABLE_HEADER_HEIGHT) / TABLE_DIVISIONS
    for division in range(1, TABLE_DIVISIONS):
        row_y = top_y - TABLE_HEADER_HEIGHT - division * row_height
        axes.plot([left_x, left_x + TABLE_WIDTH], [row_y, row_y], color=MUTED, linewidth=0.4)
    for division in range(1, TABLE_DIVISIONS):
        column_x = left_x + division * TABLE_WIDTH / TABLE_DIVISIONS
        axes.plot([column_x, column_x], [top_y - TABLE_HEIGHT, top_y], color=MUTED, linewidth=0.4)
    # One highlighted cell in the first column, second body row: the quotation found.
    highlighted_cell_y = top_y - TABLE_HEADER_HEIGHT - 2 * row_height + 0.5
    axes.add_patch(Rectangle((left_x + 0.6, highlighted_cell_y), TABLE_WIDTH / TABLE_DIVISIONS - 1.2, 1.2, facecolor=GOLD, alpha=0.7, linewidth=0))


def draw_figure():
    """Build the whole figure and return it."""
    figure = plt.figure(figsize=(WIDTH_MM / MM_PER_INCH, HEIGHT_MM / MM_PER_INCH), dpi=DPI)
    axes = figure.add_axes([0, 0, 1, 1])
    axes.set_xlim(0, WIDTH_MM)
    axes.set_ylim(0, HEIGHT_MM)
    axes.axis("off")
    stage_drawers = [draw_commentary_page, draw_text_window, draw_model, draw_verification_shield, draw_output_table]
    for centre_x, draw_stage, (title, description) in zip(STAGE_CENTRES_X, stage_drawers, STAGE_CAPTIONS):
        draw_stage(axes, centre_x)
        draw_caption(axes, centre_x, CAPTION_TOP_Y, title, description)
    for left_centre_x, right_centre_x in zip(STAGE_CENTRES_X[:-1], STAGE_CENTRES_X[1:]):
        draw_arrow(axes, left_centre_x + ARROW_GAP_MM, right_centre_x - ARROW_GAP_MM, ICON_CENTRE_Y)
    return figure


def main():
    """Draw the figure and save it as a 300 dpi PNG and as an SVG."""
    arguments = parse_arguments()
    os.makedirs(arguments.output_dir, exist_ok=True)
    output_path = os.path.join(arguments.output_dir, OUTPUT_FILE_NAME)
    figure = draw_figure()
    figure.savefig(output_path, dpi=DPI, facecolor="white")
    print("written", output_path)
    vector_output_path = os.path.join(arguments.output_dir, VECTOR_OUTPUT_FILE_NAME)
    with matplotlib.rc_context(SVG_SETTINGS):
        figure.savefig(vector_output_path, facecolor="white", metadata=SVG_METADATA)
    print("written", vector_output_path)


if __name__ == "__main__":
    main()
