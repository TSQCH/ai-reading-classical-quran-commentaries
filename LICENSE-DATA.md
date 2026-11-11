# Licence of the data

Copyright (c) 2026 Mahmoud Hammoud and Bärbel Wetenkamp

The data in this repository are licensed under the Creative Commons Attribution 4.0
International licence (CC BY 4.0):

https://creativecommons.org/licenses/by/4.0/

You may share and adapt the data for any purpose, provided that you give appropriate credit,
link to the licence and indicate whether changes were made.

The data are: the coding rule, the reference coding of the 758 positions, the answers of every
coder (`results/<coder>/*.jsonl`), the Claude blind re-run of 609 positions and the rule it was
given (`reference-coding/twelve-commentaries/stage1-output/independent-coding/`), the coding
files of the two earlier builds of packets 26 and 27
(`paper-and-two-added-commentaries/blind-coding/earlier-builds/`), the results tables and the
comparison reports.

The scripts (Python, and one Node.js script) are licensed separately, under the MIT License
(see `LICENSE`).

## Text of the classical commentaries: not covered by this licence

The text packets (`first-twelve-commentaries/second-coding-by-external-AI/data/blind-packet-*.md`)
hold 624 passages of twelve classical Qur'an commentaries, and the coding files quote
passages from them, some coders copying long stretches of a window. Eleven of the twelve
authors died centuries ago and their works are in the
public domain. The twelfth, Muḥammad al-Ṭāhir Ibn ʿĀshūr, died in 1973; his al-Taḥrīr
wa-l-tanwīr is still protected by copyright in many countries, and its 67 passages are
reproduced here only as quotations for the scholarly comparison described below, not under
any licence. Where a coder's quotation or note copied an editor's footnote from the text
served, the copied footnote text is replaced by the same mark;
`first-twelve-commentaries/second-coding-by-external-AI/results/editors-footnotes-in-answers-removed.tsv` gives the SHA-256 of each such field as the
coder returned it and as deposited.
The passages were taken from digital texts of the printed editions named in the paper. In 193 of
them the text served to the coders included footnotes of the modern editor; those footnotes are
not reproduced here, each being replaced by a mark that says so (see `README.md` and
`editors-footnotes-removed.tsv` beside the packets). The passages keep the volume and page
markers of those editions, and the vowel marks of fourteen passages of al-Ṭabarī are those of the
edition used.

These passages are reproduced only so that the coding can be checked against the text the coders
read. They are not covered by the CC BY 4.0 licence above, and any rights that the editors or
publishers of those editions hold in their text remain with them. Anyone reusing the passages
beyond scholarly comparison should cite and consult the printed editions.

The text of al-Hawwari and of Atfayyish's Himyan al-zad taken from altafsir.com (Royal Aal
al-Bayt Institute for Islamic Thought) is not part of this repository (see `README.md`), except
for the passages that the coders and the reference coding quote from it in the coding files of
the 134 positions (`paper-and-two-added-commentaries/blind-coding/results/` and
`paper-and-two-added-commentaries/blind-coding/earlier-builds/`). Those passages
are reproduced only so that the coding can be checked; they are not covered by the CC BY 4.0
licence above.
