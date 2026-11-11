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
| `reference-coding/twelve-commentaries/` | in `scripts/`, the script that cut the windows of the first set (step 1); in `stage1-output/`, the reference coding of those 624 positions (`panel-majority.json`: the 67 disputed points, their candidate views and the position of each commentary) and the blind re-run of 609 of them (`independent-coding/second-coder-positions.json`, with the rule it was given, `independent-coding/coding-rule.md`) |

## What you need

- Python 3.14 (the version the results were produced with) and the packages in
  `requirements.txt`: `python -m pip install -r requirements.txt`. Every script that only
  computes agreement uses the standard library alone.
- For step 1 only, as a record: Node.js 16 or later.
- For the open-weight models: an [Ollama](https://ollama.com) server and a graphics card. The
  models of up to nine billion parameters fit in 8 GB of card memory; those of 12 to 14 billion
  need 12 GB to run whole, and on an 8 GB card they run partly in system memory, slower but
  with the same output. Each coder's `model-info.json` names the Ollama tag that was run (for
  example `qwen3:14b`); the output budget (1,200 tokens) and the switching off of reasoning
  (`think` false for `qwen3:14b` and `deepseek-r1:14b`) are constants of the runners and are not
  recorded there. Qwen3 14B was first started with reasoning on (3 November 2026); after 52
  positions, at 311 seconds a position on average and with 11 of them in parse error because
  the reasoning used up the output budget, that run was abandoned and the model coded every
  position again with reasoning off; its answers are not deposited. DeepSeek-R1 14B was run
  with reasoning off from the start. The digests of the model files were not recorded at run time, and a tag
  can later point to a newer build, so a re-run may not use byte-identical weights.
- For Gemini: the Gemini command-line tool (the runs used Gemini CLI 0.66.0 in November 2026 with
  the model id `gemini-3-pro-preview`; the CLI's session log of every packet call of both published
  runs records the model that answered as `gemini-3.1-pro-preview`; the paper and the result tables
  name the coder Gemini 3 Pro, the name under which the id was offered; a preview model can be
  withdrawn by its vendor, so a re-run may need another id), authenticated with a Gemini API key of
  your own (the published runs used the CLI's API-key authentication, setting
  `security.auth.selectedType` = `gemini-api-key`, not a Google-account sign-in). For the archived service
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

1. `../../reference-coding/twelve-commentaries/scripts/build_blind_coding_packet.js` (Node.js)
   cut the windows of the 609 positions on 23 October 2026, and
   `scripts/build_external_ai_blind_coding_packets.py` built packets 1 to 24 from them,
   replacing 15 windows. The window cutter read the reference coding as it stood that day
   (609 positions, before rows 17, 19 and 63 of the five later commentaries were added); run
   on the deposited `panel-majority.json` it cuts 624 windows into six packets of 104, and the
   Python builder stops at its check of 609 positions.
2. `scripts/build_extra_packet_25_for_rows_17_19_63.py` built packet 25 (15 positions).
3. The blind coders: `scripts/run_blind_coding_through_gemini_cli.py` (Gemini 3 Pro) and
   `scripts/run_blind_coding_through_local_ollama_models.py` (the nine open-weight models, one
   position per call). `scripts/run_blind_coding_through_deepseek_api.py` and
   `scripts/archive/run_blind_coding_through_openai_and_gemini_apis.py` are earlier service
   runners, kept for the record. The runners skip every position already answered, so move
   `results/` out of the folder before a re-run; for Gemini this also keeps the re-run blind,
   since every coder's `disagreements.tsv` lists the reference type in its column "first".
4. `scripts/merge_external_ai_results_and_compare.py results/<coder> ../../reference-coding/twelve-commentaries/stage1-output/panel-majority.json`
   merges one coder's answers and compares them with the reference coding (Cohen's kappa, list
   of disagreements).
5. `scripts/three_coders_agreement_fleiss_kappa.py ../../reference-coding/twelve-commentaries/stage1-output results/gemini results`
   computes the three-coder agreement and Fleiss' kappa (Table 3 of the paper).

The 25 packets are in `data/`. Steps 1 and 2 are given as the record of how the packets were
cut; they read the full text of the twelve commentaries, which is not part of this repository.
The windows of the first set were not placed by searching for the disputed phrase, as those of
packets 26 and 27 were (step 7): each is the 1,500 characters on each side of the first
occurrence, in the commentator's full text, of the opening 40 (failing that 25 or 15)
characters of the quotation recorded by the reference coding, vowel marks removed. This holds
for 606 of the 624 windows as served; the exceptions are the 14 al-Ṭabarī windows replaced by
his verified passage on the phrase (rows 2, 9, 12, 24, 25, 39, 44, 46, 48, 49, 50, 51, 53, 60),
row 9 of Ibn ʿAṭiyya (cut around the quotation in his text of sura 80, because its first
occurrence in the whole commentary lies in another sura), the two windows of the positions the
reference coding has as silent, and row 63 of Ibn ʿAṭiyya in packet 25 (cut around the last word
of the phrase, because no opening of the quotation is found in his text of sura 108). In packet 25 the
quotations of Ibn ʿAṭiyya are searched in his text of the sura only. The quotation is not
marked in the window, but where the window falls was taken from the reference coding.
Two windows (row 36, Ibn Juzayy, in packet 13; row 43, al-Bayḍāwī, in packet 15) hold only the
note that no passage was found; they are the two positions the reference coding has as silent.

The windows served to the coders were cut from digital texts of printed editions, and 193 of the
624 took in footnotes of the modern editor (al-Qurṭubī 66, Ibn Juzayy 59, al-Thaʿālibī 31, Abū
Ḥayyān 19, al-Rāzī 10, Ibn ʿĀshūr 7, al-Khāzin 1). That apparatus is the editor's text, not the
commentator's, so it is not redistributed: in the deposited packets each footnote block (300 in
all: 287 after the editor's rule of underscores, and 13 at the start of a window whose cut began
inside the footnotes of the previous page, up to the first volume/page marker) is replaced by
this mark, which means "editor's footnote removed":

> [حاشية المحقق محذوفة]

Nothing else was changed; `data/editors-footnotes-removed.tsv` lists every window concerned with the SHA-256
digests of the window as served and as deposited. The removal was made by the script that
assembled this deposit from the authors' working folders, which is not part of it because it
reads those folders. Every figure of the paper was computed on the windows as served.
A re-run of step 3 on the deposited packets therefore serves 193 windows without the editors'
footnotes, unlike the published runs; its answers on those positions can differ for that
reason alone, even with the same model weights.

Some coders copied long stretches of their window, footnotes included, into the quotation or the
note of an answer. Where a coder's quotation or note copied an editor's footnote from the text
served, the copied footnote text is replaced by the same mark, in 59 fields (every run of 20 or
more characters shared with a footnote removed from the same window, unless the run is also
the commentator's own text; shorter fragments, such as the editor's rule of underscores at the
end of a quotation, are left). This is done in each coder's answer files and merged file
(AceGPT-v2 8B 16 fields, ALLaM 7B 24, Jais 13B 11, DeepSeek-R1 14B 3, Falcon-H1 7B 3, Qwen3 14B 2;
no Gemini 3 Pro field needed it, so `results/three-coders-disagreements.tsv` is unchanged);
`results/editors-footnotes-in-answers-removed.tsv` gives the SHA-256 of each such field as the
coder returned it and as deposited. The agreement tables (Tables 1 to 3) read only the type and
the views held, so they are unchanged.

**B. The two commentaries added for this paper, 134 positions** (`paper-and-two-added-commentaries/`)

6. `scripts/download_ibadi_tafsirs_juz_amma_from_altafsir_com.py` downloads the text of
   al-Hawwārī and of Aṭfayyish's Himyān al-zād on Juzʾ ʿAmma.
7. `scripts/build_blind_packets_hawwari_and_himyan.py ../reference-coding/twelve-commentaries/stage1-output/panel-majority.json` cuts the text
   windows (packets 26 and 27). `blind-coding/packets-26-27-sha256-as-served.txt` gives the
   SHA-256 of the two packets as served (line ends read as LF); a rebuilt packet with another
   digest was cut from text that has changed on the site since 4 November 2026.
8. The blind coders: `blind-coding/scripts/run_blind_coding_through_gemini_cli.py` and
   `blind-coding/scripts/run_blind_coding_through_local_ollama_models.py`. The Gemini CLI runs
   with the `blind-coding` folder as its workspace, which holds the reference coding in
   `results/claude/` and `earlier-builds/`, and every coder's `disagreements.tsv` beside the
   reference; move `results/` and `earlier-builds/` out while Gemini runs, so that the re-run stays blind
   (the CLI's session logs of the published runs show no tool call and no file read).

Packets 26 and 27 were built three times on the night of 3 to 4 November 2026 (windows on
al-Ṭabarī's unit ranges, then windows anchored on the phrase, then the build of step 7), and
Gemini coded each build; the reference coding was first made on the first build and revised on
the final one, after Gemini's answers on the first two builds existed. The final reference
differs from the first on the type in 9 of the 134 positions, six of them towards the type
Gemini had given on an earlier build (five where the earlier window had missed the passage).
Against the final reference Gemini agrees on the type in 121, 124 and 126 of 134 positions on
the three builds; Table 2 reports the third. `blind-coding/earlier-builds/` holds the reference
coding of the first build and Gemini's answers on the first two builds, with the SHA-256 of the
earlier packets (`packets-26-27-earlier-builds-sha256.txt`, line ends read as LF); the earlier packets themselves are
altafsir.com text and are not redistributed.
9. `blind-coding/scripts/compare_oman_coders_against_claude_reference.py` compares every coder
   with the reference coding.

**The rescue pass of the positions left in parse error** (Section 4.2 of the paper)

The first runs of the open-weight models left 46 positions in parse error, 41 of the first set
and 5 of the second. One of them, Jais 13B on row 64 of Ibn Juzayy, was a server failure, not
an answer: the Ollama server returned HTTP 500 on every call, and the position was recorded as
a parse error by hand so that it counted as a disagreement; it failed in the same way in the
repetition of 7 November and was coded under the length limit. These positions, and no others,
were coded again with the two scripts of
`first-twelve-commentaries/second-coding-by-external-AI/scripts/`, which serve both sets:
`remove_parse_error_records_for_recoding.py` removes the parse-error records of one coder (after
keeping a copy), so that the runner of step 3 or 8 codes those positions again with unchanged
settings, and `recode_failed_positions_with_answer_length_cap.py` runs the same runner with a
maximum length of 200 characters on the quotation and the note, for the positions repetition
could not recover. The deposited `positions.jsonl` hold the final answers. The 46 records of
the rescue pass are the only ones that carry the key `verification`; the 34 coded under the
length limit also carry `answer_length_cap`. No parse error remains.
A first attempt of 5 November 2026, left unfinished, was discarded and the pass was run again
from the answers of the first runs on 7 November; in it DeepSeek-R1 14B had answered all 8 of
its positions, and its two answers differ in type on 4 of them (rows 11 and 40 of al-Ṭabarī,
38 and 64 of al-Qurṭubī); Jais 13B had answered 2 of its 22 (row 5 of al-Ṭabarī and of
al-Bayḍāwī) and AceGPT-v2 8B 4 of its 9 (row 21 of Ibn ʿAṭiyya, 52 of al-Khāzin, 60 of al-Rāzī,
61 of Abū al-Suʿūd), and ALLaM 7B had not been reached. Four of these (the two of Jais, rows 21
and 61 of AceGPT) failed again on 7 November and are among the 34 coded under the length limit,
with the type they had on 5 November. Identical settings therefore did not give identical
output across the two attempts. The deposited records are those of 7 November.

**C. Results of the paper** (`paper-and-two-added-commentaries/`)

10. `scripts/build_all_coders_results_tables.py` builds Tables 1 and 2 from the coding files.
11. `scripts/verify_blind_coders_quotations_against_windows.py --out-dir <folder>` checks every
    quotation against the window served (Table 4); without `--out-dir` it replaces the
    published report in `blind-coding/results/`.
12. `human-coding/scripts/build_human_coding_sample_100_positions.py` draws the stratified
    sample for the independent human coding named in Section 6.3.

**D. The figure and the layout of the paper** (`paper-and-two-added-commentaries/`)

13. `scripts/snm05-v09/draw_snm05_figure_1_source_bound_pipeline.py` draws Figure 1 (PNG and SVG),
    with the "Model" caption of the final version of the paper ("nine open-weight models, one
    position per call, temp. 0; Claude, Gemini: packets"); the submitted version reads
    "temperature 0, one position per call: Claude, Gemini, or nine open-weight models".
14. `scripts/build_springer_lncs_reference_docx_for_pandoc.py` builds the layout document, and
    `scripts/build_snm05_paper_docx_and_pdf.py <draft.md>` builds a .docx and a .pdf from a
    Markdown draft.

Steps 4, 5, 9 and 10 recompute the agreement figures of Tables 1 to 3 from the deposited coding
files in a few seconds; they need no model, no network and no graphics card. On Windows the
files they rewrite are byte-identical to the deposited ones; on Linux or macOS most of them come
out with LF line ends where the deposited files have CRLF, so compare them with
`diff --strip-trailing-cr`. One row is quoted,
not recomputed: the first row of Table 1 (the Claude blind re-run against the first coding
before adjudication), because that first coding is not deposited; against the deposited,
adjudicated coding the re-run agrees on the type in 583 of 609 positions (Table 3).
The re-run was made on 23 October 2026 by twelve subagents of one Claude Code session, about
51 positions each, on six packets of 99 to 102 positions cut by `build_blind_coding_packet.js`
(step 1), under `independent-coding/coding-rule.md`, a shorter wording of the rule of the
coding prompt. Fifteen of its windows had fallen in the wrong sura (14 of al-Ṭabarī, row 9 of
Ibn ʿAṭiyya); after the comparison with the first coding had shown this, they were cut again
around the occurrence of the reference quotation nearest the cited page and those positions
were coded again by a fresh subagent (type kappa against the first coding 0.85 before, 0.89
after). The six packets are not deposited; they hold the same windows as packets 1 to 24
except those fifteen. The answers
of the first runs that were left in parse error are not deposited either; the 46 records that
replaced them carry the key `verification`. Steps 11 and 12
also need packets 26 and 27, hence steps 6 and 7 first. Step 11 run on the deposited packets
differs from Table 4 on 12 quotations of the first set, which the models took partly from the
editors' footnotes now removed: Qwen3 14B 464 verbatim becomes 460, Gemma 3 12B 486 becomes
484, Falcon-H1 7B 411 becomes 410, AceGPT-v2 8B 425 becomes 424 and ALLaM 7B 275 becomes 271,
each moving to "not found" (ALLaM's share becomes 44 %); every other figure of Table 4 is unchanged. The published report
(`blind-coding/results/Quotation-check-of-all-blind-coders.md`) is the one computed on the
windows as served. Steps 3 and 8 are the long ones: two to
seven seconds per position for the models of up to nine billion parameters on an 8 GB card that
no other run shares (the Sec./pos. column of Table 1), 20 to 162 seconds for the larger ones; on
the second set the cards were shared with other runs, and Falcon-H1 7B and AceGPT-v2 8B took 31
seconds a position, Fanar 9B 8 (Table 2).
Those means include the calls of the rescue pass in place of the failed first calls (Jais 13B
34 s on each set before the pass).

`arabic_text_fold.py` exists in both project folders as identical copies, and each folder has
its own version of the two runners (same design, different packets and paths), so that each
folder runs on its own.

## Fields of the data files

- `panel-majority.json`: one record per disputed point: `n` (row, 1 to 67), `sura`, `suraAr`,
  `unit` (al-Ṭabarī's verse range, `sura:first-last`), `phrase`, `views` (`id`, `label_ar`) and
  `positions`, keyed by commentator code, each with `type`, `holds` (view ids), `quote` (the
  reference quotation; null for the two silent positions), `page` (volume/page of the edition
  used; null for the two silent positions), `source` (the text in which the quotation was located by machine: `lib:<name>`
  a full digital text of the commentary, `packet` the passage prepared for the reference
  coding; neither is deposited) and `ok` (true when that check found the quotation, and for
  the two silent positions, which have none; true for all 624).
- `independent-coding/second-coder-positions.json`: one object per position re-coded blind:
  `n`, `who`, `type`, `holds`, `evidence` (the quotation the re-run gave) and `note`.
- `results/<coder>/*.jsonl`: `row`, `who`, `type`, `holds`, `quote` and `note` as the coder
  returned them, except that the local runners set `row` and `who` from the packet header and
  that 59 quotations or notes of the first set had copied footnotes replaced (part A); the
  local runners add `seconds` (wall-clock time of the call); the 46 records of the rescue pass
  add `verification` (the list of content checks the answer failed, empty in 27 of them) and the 34 coded under the
  length limit `answer_length_cap` (200). `results/claude/*.jsonl` of the second set is the
  reference coding of the 134 positions, in the same form.

## Source and generated files

Source: the scripts, the coding rule (`Blind-coding-prompt-for-external-AI-coder-*.md`), the
packets, the reference coding, the answers of every coder (`results/<coder>/*.jsonl`) and the
coding files of the earlier builds of packets 26 and 27 (`blind-coding/earlier-builds/`).

Generated, and rebuilt by the steps above: `merged-positions.json` and `disagreements.tsv` of
every coder, the two three-coder tables, the results tables, the quotation check, the figure
and the layout document.

## Changes in version 1.0.1

No coding file used by Tables 1 to 4 changed. Corrected: version 1.0.0 did not say how the
windows of the first set were placed; they were placed around the quotation recorded by the
reference coding (paragraph after step 5), and the script that cut them is now deposited
(`reference-coding/twelve-commentaries/scripts/build_blind_coding_packet.js`, step 1).
Added: the rule given to the Claude blind re-run (`independent-coding/coding-rule.md`) and the
paragraph on how the re-run was made; the section "Fields of the data files"; the advice in
steps 3 and 8 to move `results/` out before a re-run; the note that a re-run of step 3 serves
the windows without the editors' footnotes; the server failure of Jais 13B on row 64 of Ibn
Juzayy; the first run of Qwen3 14B with reasoning on; `paper-and-two-added-commentaries/
blind-coding/earlier-builds/` (the reference coding of the first build of packets 26 and 27,
Gemini's answers on the first two builds and the digests of those packets) and the paragraph
on the three builds after step 8; the digests of packets 26 and 27 as served; the model recorded
by the Gemini CLI's session logs (`gemini-3.1-pro-preview`); the record of the Gemini packet
sessions of the first set; the discarded first attempt of the rescue pass; the status of the
altafsir.com passages quoted in the coding files and of Ibn ʿĀshūr's passages in the packets;
`.gitattributes`, which keeps every file's line ends as deposited whatever the git settings;
corrections to docstrings and to the downloader's handling of empty pages. Changed in what
the scripts do: the "Model" caption of Figure 1 (step 13); the paper build removes an older PDF
and stops when Word writes none; the DeepSeek runner accepts only deepseek-reasoner and
deepseek-chat; the archived API runner counts a packet as done when it has one line per
position of that packet.

## Licence

The scripts are under the MIT License (`LICENSE`). The data are under the Creative Commons
Attribution 4.0 International licence, CC BY 4.0 (`LICENSE-DATA.md`). The text of the classical
commentaries in the 25 packets, and the passages quoted from it and from the altafsir.com text in
the coding files, are not
covered by either licence: they are reproduced for scholarly comparison, as `LICENSE-DATA.md`
explains. How to cite the deposit is in `CITATION.cff`.

## Not in this repository

1. The text of the two commentaries downloaded from altafsir.com, and the packets cut from it
   (packets 26 and 27), are not redistributed here; only the passages that the coders and the
   reference coding quote from it remain in the coding files, as `LICENSE-DATA.md` explains.
   Steps 6 and 7 fetch and rebuild the packets.
2. The full text of the first twelve commentaries. The windows served to the coders are in the
   25 packets, without the editors' footnotes (see part A above).
3. The text of the paper.
4. The logs of the runs and the dated run reports that some docstrings name.
5. The watchdog that restarted interrupted runs, and the other helper scripts of the office
   machines.
6. A script that writes the per-point table described in Section 3.6 of the paper (one row per
   commentator with type, views held, quotation, place in the edition and verification flag).
   The deposit holds the evaluation: each coder's answers (`results/<coder>/*.jsonl`) and the
   scripts that compare them with the reference coding; the place in the edition is recorded
   only in the reference coding (`page` in `panel-majority.json`).
