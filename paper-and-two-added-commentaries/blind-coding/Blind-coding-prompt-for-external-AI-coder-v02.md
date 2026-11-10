# Prompt for the external AI coder

Paste everything below the line into a new conversation with the AI (ChatGPT, Gemini or another), then attach or paste ONE packet file from the `data` folder. Repeat in a fresh conversation for each of the 24 packets. Save each answer as `results\<model-name>\blind-packet-NN-of-24.jsonl` (for example `results\gpt\blind-packet-01-of-24.jsonl`). Nothing in the packets or in this prompt tells the AI what the first coder decided.

---

You are an expert reader of classical Arabic Qur'an commentary (tafsīr). You will code, one by one, the positions of classical Qur'an commentators on disputed phrases of the last part of the Qur'an (Juzʾ ʿAmma). Work only from the Arabic text given to you. Do not use any knowledge of what other scholars or earlier studies decided, and do not guess from the commentator's reputation.

## The material

The attached file contains a numbered list of positions. Each position has a header line of the form

`## <row> | <sura and verses> | <disputed phrase> | <commentator>`

followed by a line `views:` that lists the candidate views recorded for this phrase, each with an id (V1, V2 ..., N1, N2 ...) and an Arabic label, and then a window of the commentator's own text taken from his commentary around the place where he discusses this phrase. The commentator codes are: tabari = al-Ṭabarī, razi = Fakhr al-Dīn al-Rāzī, qurtubi = al-Qurṭubī, baydawi = al-Bayḍāwī, ibnJuzayy = Ibn Juzayy, khazin = al-Khāzin, ibnAshur = Ibn ʿĀshūr, ibnAtiyya = Ibn ʿAṭiyya, thaalibi = al-Thaʿālibī, abuHayyan = Abū Ḥayyān, abuSaud = Abū al-Suʿūd, nasafi = al-Nasafī, hawwari = Hūd ibn Muḥakkam al-Hawwārī, himyan = Muḥammad ibn Yūsuf Aṭfayyish (Himyān al-zād).

## The counting rule, to apply strictly and identically to every position

Each commentator's position on a phrase is exactly one of five types:

- **prefers**: he gives more than one view, then explicitly chooses one (a word of choice such as al-ṣawāb, awlā, al-aẓhar, al-aqrab, al-mukhtār, al-ṣaḥīḥ, aṣaḥḥ, arjaḥ, aqwā, when it ranks one view over the others), OR he argues explicitly for one view against the others so that his choice is clear (for example calling every other view weak or far-fetched while keeping one).
- **single**: he states only ONE meaning in his own voice and gives no sign that other views exist. If that one meaning is introduced with qīla ("it is said"), he is reporting, not holding: that is NOT single (record lists_no_choice).
- **combines**: he states that the phrase covers all or both views, or that they do not conflict. EXCEPTION: if the general or comprehensive meaning is itself one of the listed views (a view label meaning "general", "all", "every ..."), then choosing it is a vote for that view: record prefers (if with a word of choice or an argument) or single, holding that view's id.
- **lists_no_choice**: he gives several views and does not choose.
- **silent**: the window does not address this phrase at all.

Not a choice (stays lists_no_choice): calling a view ḥasan or qawī without placing it above the others; his own gloss stated before he reports the dispute, without a word of choice; attributing a view to the majority (al-jumhūr, al-akthar, akthar al-mufassirīn) without adopting it in his own words; quoting someone else's preference (for example "wa-ikhtārahu al-Ṭabarī", "qāla al-Wāḥidī: wa-l-awlā") without endorsing it; a preference word that concerns a reading (qirāʾa), grammar (iʿrāb) or another question, not the meaning in dispute.

Only prefers and single are votes.

## What to return

Return ONLY a JSON Lines block: one JSON object per position, in the order of the file, no commentary before or after. Each object has these keys:

- `row`: the row number from the header (integer)
- `who`: the commentator code from the header
- `type`: one of prefers, single, combines, lists_no_choice, silent
- `holds`: the list of view ids he holds (for prefers and single exactly one id; for combines the ids combined; for lists_no_choice the ids he lists; for silent an empty list). If a view he states is not among the listed views, write "OTHER" and put its Arabic wording in `note`.
- `quote`: the shortest verbatim Arabic passage (one clause or sentence, copied exactly from the window) that justifies the type you gave; empty string for silent.
- `note`: a short remark only where the decision was difficult, otherwise an empty string.

Example of one line:

{"row": 1, "who": "razi", "type": "prefers", "holds": ["V2"], "quote": "وهذا هو الأقرب", "note": ""}

Code every position in the file. Do not skip any. Do not stop before the last position; if the file is long, continue until every header has one line.
