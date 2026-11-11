// Builds the blind packets of the Claude blind re-run (23 October 2026); kept unchanged as the record of that run.
// For every position of the reference coding (../stage1-output/panel-majority.json): the header "## row | sura unit |
// phrase | commentator", the candidate views, and a window of the commentator's full text from the library copy, without
// the reference type, held views or quotation. The window is placed by the reference quotation: quotation and text are
// stripped of vowel marks, superscript alif and tatweel (MARKS) and their whitespace collapsed; the first 40, else 25,
// else 15 characters of the quotation are searched in the text, and the window is the 1,500 characters before and after
// the start of the first match. A position without a quotation, or whose quotation is not found, gets the note
// "(no passage found ...)". The positions are split into six packets of equal size (the last may be shorter).
// Names: F commentator -> text file; T(w) the normalised text of commentator w (cached); d the reference coding;
// r one point, w a commentator code, p his position; q the normalised quotation, i the offset found, L a prefix length.
// Writes ../stage1-output/independent-coding/blind-packet-<k>.md, k = 1 to 6.
// Run from this folder:  node build_blind_coding_packet.js <folder of converted texts>   (Node.js 16 or later)
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, ".."), OUT = path.join(ROOT, "stage1-output", "independent-coding");
const LIB = process.argv[2];
const F = { tabari: "tabari-hajr.txt", razi: "razi.txt", qurtubi: "qurtubi.txt", baydawi: "baydawi.txt", ibnJuzayy: "ibn-juzayy.txt", khazin: "khazin.txt",
  thaalibi: "thaalibi.txt", ibnAtiyya: "ibn-atiyya.txt", ibnAshur: "ibn-ashur.txt", abuHayyan: "abu-hayyan.txt", abuSaud: "abu-saud.txt", nasafi: "nasafi.txt" };
const MARKS = /[\u064B-\u0652\u0670\u0640]/g;
const cache = {};
const T = (w) => cache[w] ??= fs.readFileSync(path.join(LIB, F[w]), "utf8").replace(MARKS, "").replace(/\s+/g, " ");
const d = JSON.parse(fs.readFileSync(path.join(ROOT, "stage1-output", "panel-majority.json"), "utf8"));
const items = [];
for (const r of d) for (const [w, p] of Object.entries(r.positions)) {
  let text = "(no passage found: he does not address this phrase where expected)";
  if (p.quote) { const t = T(w), q = p.quote.replace(MARKS, "").replace(/\s+/g, " ").trim();
    let i = -1; for (const L of [40, 25, 15]) { i = t.indexOf(q.slice(0, L)); if (i >= 0) break; }
    if (i >= 0) text = t.slice(Math.max(0, i - 1500), i + 1500); }
  items.push(`## ${r.n} | ${r.suraAr} ${r.unit} | ${r.phrase} | ${w}\nviews: ${r.views.map((v) => v.id + " = " + v.label_ar).join(" ; ")}\n\n${text}\n`);
}
const per = Math.ceil(items.length / 6);
for (let k = 0; k < 6; k++) fs.writeFileSync(path.join(OUT, `blind-packet-${k + 1}.md`), items.slice(k * per, (k + 1) * per).join("\n"));
console.log(items.length, "positions in 6 packets");
