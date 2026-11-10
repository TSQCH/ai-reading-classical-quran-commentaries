# AI-Powered Reading of Classical Qur'an Commentaries: code and data

Code and data behind the paper "AI-Powered Reading of Classical Qur'an Commentaries: A Source-Bound
Application Tested on Eleven Language Models" by Mahmoud Hammoud and Bärbel Wetenkamp (SNM05
"AI-Powered Applications", University of Nizwa, Oman, 15 November 2026).

The application gives a language model one passage of one named classical commentary and asks it
to classify the commentator's stance on a disputed point (prefers, single view, combines, lists
without choosing, silent) and to quote the passage verbatim. The paper measures eleven models
against a verified reference coding of 758 positions: 67 disputed points of Juzʾ ʿAmma in
fourteen commentaries.

## Layout

The three folders are siblings, and the scripts find each other's files through that layout,
so keep them side by side.

| Folder | Holds |
|---|---|
| `paper-and-two-added-commentaries/scripts/` | the results tables, the quotation check, the downloader and packet builder for the two commentaries added for this paper, the figure and the .docx and .pdf build |
| `paper-and-two-added-commentaries/blind-coding/` | the coding rule, the runners, the reference coding and the answers of every coder for the 134 positions of al-Hawwārī and Aṭfayyish, and the results tables |
| `paper-and-two-added-commentaries/human-coding/` | the script that draws the sample of 100 positions for the human coding |
| `first-twelve-commentaries/second-coding-by-external-AI/` | the coding rule, the 25 packets, the packet builders, the runners, the answers of every coder and the agreement scripts for the 624 positions of the first twelve commentaries |
| `reference-coding/twelve-commentaries/stage1-output/` | the reference coding of those 624 positions (`panel-majority.json`: the 67 disputed points, their candidate views and the position of each commentary) and the blind re-run of 609 of them (`independent-coding/second-coder-positions.json`) |

## What you need

- Python 3.14 (the version the results were produced with) and the packages in
  `requirements.txt`: `python -m pip install -r requirements.txt`. Every script that only
  computes agreement uses the standard library alone.
- For the open-weight models: an [Ollama](https://ollama.com) server and a graphics card. The
  models of up to nine billion parameters fit in 8 GB of card memory; those of 12 to 14 billion
  need 12 GB to run whole, and on an 8 GB card they run partly in system memory, slower but
  with the same output. Each coder's `model-info.json` names the Ollama tag that was run (for
  example `qwen3:14b`). The digests of the model files were not recorded at run time, and a tag
  can later point to a newer build, so a re-run may not use byte-identical weights.
- For Gemini 3 Pro: the Gemini command-line tool (the runs used Gemini CLI 0.66.0 with the model
  id `gemini-3-pro-preview` in November 2026; a preview model can be withdrawn by its vendor, so a
  re-run may need another id), signed in to an account of your own. For the archived service
  runners: an API key of your own, given in an environment variable or in a
  file of a `_secrets` folder beside the three folders, as each script's docstring describes.
  `.gitignore` keeps that folder out of the repository, and no key is stored in it.
- For the paper build: pandoc (brought by `pypandoc_binary`). The PDF is exported through
  Microsoft Word on Windows; on Linux or macOS the build writes the .docx and says so.

Every script states in its docstring what it reads, what it writes and how to run it; the
scripts that take arguments list them with `python <script> --help`.

## Order of the pipeline

Run from the folder named in each step.

**A. The first twelve commentaries, 624 positions** (`first-twelve-commentaries/second-coding-by-external-AI/`)

1. `scripts/build_external_ai_blind_coding_packets.py` built packets 1 to 24 (609 positions).
2. `scripts/build_extra_packet_25_for_rows_17_19_63.py` built packet 25 (15 positions).
3. The blind coders: `scripts/run_blind_coding_through_gemini_cli.py` (Gemini 3 Pro) and
   `scripts/run_blind_coding_through_local_ollama_models.py` (the nine open-weight models, one
   position per call). `scripts/run_blind_coding_through_deepseek_api.py` and
   `scripts/archive/run_blind_coding_through_openai_and_gemini_apis.py` are earlier service
   runners, kept for the record.
4. `scripts/merge_external_ai_results_and_compare.py results/<coder> ../../reference-coding/twelve-commentaries/stage1-output/panel-majority.json`
   merges one coder's answers and compares them with the reference coding (Cohen's kappa, list
   of disagreements).
5. `scripts/three_coders_agreement_fleiss_kappa.py ../../reference-coding/twelve-commentaries/stage1-output results/gemini results`
   computes the three-coder agreement and Fleiss' kappa (Table 3 of the paper).

The 25 packets are in `data/`. Steps 1 and 2 are given as the record of how the packets were
cut; they read the full text of the twelve commentaries, which is not part of this repository.

The windows served to the coders were cut from digital texts of printed editions, and 193 of the
624 took in footnotes of the modern editor (al-Qurṭubī 66, Ibn Juzayy 59, al-Thaʿālibī 31, Abū
Ḥayyān 19, al-Rāzī 10, Ibn ʿĀshūr 7, al-Khāzin 1). That apparatus is the editor's text, not the
commentator's, so it is not redistributed: in the deposited packets each footnote block (300 in
all: 287 after the editor's rule of underscores, and 13 at the start of a window whose cut began
inside the footnotes of the previous page, up to the first volume/page marker) is replaced by
this mark, which means "editor's footnote removed":

> [حاشية المحقق محذوفة]

Nothing else was changed; `data/editors-footnotes-removed.tsv` lists every window concerned with the SHA-256
digests of the window as served and as deposited, and the deposit builder
(`paper-and-two-added-commentaries/scripts/assemble_snm05_repository_deposit_for_github_and_zenodo.py`)
does the removal. Every figure of the paper was computed on the windows as served.

Some coders copied long stretches of their window, footnotes included, into the quotation or the
note of an answer. Where a coder's quotation or note copied an editor's footnote from the text
served, the copied footnote text is replaced by the same mark, in 59 fields (every run of 20 or
more characters shared with a footnote removed from the same window, unless the run is also
the commentator's own text). This is done in each coder's answer files and merged file and in
the Gemini columns of `results/three-coders-disagreements.tsv`;
`results/editors-footnotes-in-answers-removed.tsv` gives the SHA-256 of each such field as the
coder returned it and as deposited. The agreement tables (Tables 1 to 3) read only the type and
the views held, so they are unchanged.

**B. The two commentaries added for this paper, 134 positions** (`paper-and-two-added-commentaries/`)

6. `scripts/download_ibadi_tafsirs_juz_amma_from_altafsir_com.py` downloads the text of
   al-Hawwārī and of Aṭfayyish's Himyān al-zād on Juzʾ ʿAmma.
7. `scripts/build_blind_packets_hawwari_and_himyan.py ../reference-coding/twelve-commentaries/stage1-output/panel-majority.json` cuts the text
   windows (packets 26 and 27).
8. The blind coders: `blind-coding/scripts/run_blind_coding_through_gemini_cli.py` and
   `blind-coding/scripts/run_blind_coding_through_local_ollama_models.py`.
9. `blind-coding/scripts/compare_oman_coders_against_claude_reference.py` compares every coder
   with the reference coding.

**The rescue pass of the positions left in parse error** (Section 4.2 of the paper)

The first runs of the open-weight models left 46 positions in parse error, 41 of the first set
and 5 of the second. These positions, and no others, were coded again with the two scripts of
`first-twelve-commentaries/second-coding-by-external-AI/scripts/`, which serve both sets:
`remove_parse_error_records_for_recoding.py` removes the parse-error records of one coder (after
keeping a copy), so that the runner of step 3 or 8 codes those positions again with unchanged
settings, and `recode_failed_positions_with_answer_length_cap.py` runs the same runner with a
maximum length of 200 characters on the quotation and the note, for the positions repetition
could not recover. The deposited `positions.jsonl` hold the final answers. The 46 records of
the rescue pass are the only ones that carry the key `verification`; the 34 coded under the
length limit also carry `answer_length_cap`. No parse error remains.

**C. Results of the paper** (`paper-and-two-added-commentaries/`)

10. `scripts/build_all_coders_results_tables.py` builds Tables 1 and 2 from the coding files.
11. `scripts/verify_blind_coders_quotations_against_windows.py` checks every quotation against
    the window served (Table 4).
12. `human-coding/scripts/build_human_coding_sample_100_positions.py` draws the stratified
    sample for the independent human coding named in Section 6.3.

**D. The figure and the layout of the paper** (`paper-and-two-added-commentaries/`)

13. `scripts/snm05-v09/draw_snm05_figure_1_source_bound_pipeline.py` draws Figure 1 (PNG and SVG).
14. `scripts/build_springer_lncs_reference_docx_for_pandoc.py` builds the layout document, and
    `scripts/build_snm05_paper_docx_and_pdf.py <draft.md>` builds a .docx and a .pdf from a
    Markdown draft.

Steps 4, 5, 9 and 10 recompute the agreement figures of Tables 1 to 3 from the deposited coding
files in a few seconds; they need no model, no network and no graphics card. One row is quoted,
not recomputed: the first row of Table 1 (the Claude blind re-run against the first coding
before adjudication), because that first coding is not deposited; against the deposited,
adjudicated coding the re-run agrees on the type in 583 of 609 positions (Table 3). The answers
of the first runs that were left in parse error are not deposited either; the 46 records that
replaced them carry the key `verification`. Steps 11 and 12
also need packets 26 and 27, hence steps 6 and 7 first. Step 11 run on the deposited packets
differs from Table 4 on 12 quotations of the first set, which the models took partly from the
editors' footnotes now removed: Qwen3 14B 464 verbatim becomes 460, Gemma 3 12B 486 becomes
484, Falcon-H1 7B 411 becomes 410, AceGPT-v2 8B 425 becomes 424 and ALLaM 7B 275 becomes 271,
each moving to "not found"; every other figure of Table 4 is unchanged. The published report
(`blind-coding/results/Quotation-check-of-all-blind-coders.md`) is the one computed on the
windows as served. Steps 3 and 8 are the long ones: two to
seven seconds per position for the models of up to nine billion parameters on an 8 GB card, 30
to 160 seconds for the larger ones.

`arabic_text_fold.py` exists in both project folders as identical copies, and each folder has
its own version of the two runners (same design, different packets and paths), so that each
folder runs on its own.

## Source and generated files

Source: the scripts, the coding rule (`Blind-coding-prompt-for-external-AI-coder-*.md`), the
packets, the reference coding and the answers of every coder (`results/<coder>/*.jsonl`).

Generated, and rebuilt by the steps above: `merged-positions.json` and `disagreements.tsv` of
every coder, the two three-coder tables, the results tables, the quotation check, the figure
and the layout document.

## Licence

The scripts are under the MIT License (`LICENSE`). The data are under the Creative Commons
Attribution 4.0 International licence, CC BY 4.0 (`LICENSE-DATA.md`). The text of the classical
commentaries in the 25 packets, and the passages quoted from it in the coding files, are not
covered by either licence: they are reproduced for scholarly comparison, as `LICENSE-DATA.md`
explains. How to cite the deposit is in `CITATION.cff`.

## Not in this repository

1. The text of the two commentaries downloaded from altafsir.com, and the packets cut from it
   (packets 26 and 27), are not redistributed here. Steps 6 and 7 fetch and rebuild them.
2. The full text of the first twelve commentaries. The windows served to the coders are in the
   25 packets, without the editors' footnotes (see part A above).
3. The text of the paper.
4. The logs of the runs and the dated run reports that some docstrings name.
5. The watchdog that restarted interrupted runs, and the other helper scripts of the office
   machines.
