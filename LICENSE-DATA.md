# Licence of the data

Copyright (c) 2026 Mahmoud Hammoud and Bärbel Wetenkamp

The data in this repository are licensed under the Creative Commons Attribution 4.0
International licence (CC BY 4.0):

https://creativecommons.org/licenses/by/4.0/

You may share and adapt the data for any purpose, provided that you give appropriate credit,
link to the licence and indicate whether changes were made.

The data are: the coding rule, the reference coding of the 758 positions, the answers of every
coder (`results/<coder>/*.jsonl`), the results tables and the comparison reports.

The Python scripts are licensed separately, under the MIT License (see `LICENSE`).

## Text of the classical commentaries: not covered by this licence

The text packets (`first-twelve-commentaries/second-coding-by-external-AI/data/blind-packet-*.md`)
hold 624 passages of twelve classical Qur'an commentaries, and the coding files quote short
passages from them. Where a coder's quotation or note copied an editor's footnote from the text
served, the copied footnote text is replaced by the same mark; `editors-footnotes-in-answers-removed.tsv`
gives the SHA-256 of each such field as the coder returned it and as deposited. Their authors died centuries ago and their works are in the public domain.
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

Text taken from altafsir.com is not part of this repository (see `README.md`).
