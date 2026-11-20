#!/usr/bin/env python
r"""Batch-generate Hebrew LyX lecture notes from transcripts with the Gemini API.

Scans C:\Users\ronmg\Documents\Transcripts\Server for *_transcript.txt (+ *_frames folders), works out
the course of each one, sends transcript + board pictures (+ the course's slide PDFs) + the notes rules
to Gemini, and writes the returned LyX notes into the course's lecs folder. Gemini writes only the
LyX body; the header, title and macros come from Ron's own cc_lec2.lyx / cc_lec4.lyx, so the format
stays his.

Setup (once):   pip install google-genai          (API key: the GEMINI_API_KEY environment variable)
Usage:
    python batch_lyx_generator.py --dry-run          show what would be sent (no API calls)
    python batch_lyx_generator.py                    process every transcript not done before
    python batch_lyx_generator.py --combine          one file per course (e.g. ata_lec1-3.lyx)
    python batch_lyx_generator.py --only "Lecture 3" only transcripts whose name contains this
    python batch_lyx_generator.py --force            redo transcripts already in the manifest
    python batch_lyx_generator.py --model gemini-2.5-pro --max-frames 80
An existing notes file is never overwritten: the new one is saved as <name>.gemini.lyx instead.
Every run is recorded in generated_manifest.json next to this script.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

TRANSCRIPTS = r"C:\Users\ronmg\Documents\Transcripts\Server"
SEM = r"C:\University\Semester 7"
CC_LECS = os.path.join(SEM, "Computational Complexity", "lecs")
HEADER_SRC = os.path.join(CC_LECS, "cc_lec2.lyx")   # header / preamble / title format
MACROS_SRC = os.path.join(CC_LECS, "cc_lec4.lyx")   # macro paragraph (\mathsf versions, PH macros)
LYX_EXE = r"C:\Program Files\LyX 2.5\bin\lyx.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "generated_manifest.json")

# Courses: how to recognise a transcript, where notes go, and which slide decks go along.
COURSES = {
    "ata": {
        "name": "נושאים מתקדמים באלגוריתמים",
        "folder": os.path.join(SEM, "Advanced Topics in Algorithms", "lecs"),
        "match": r"SSSP|LDD|[Ss]trongly polynomial|[Ss]hortcut|[Ee]xpander|[Ff]low|[Mm]atching|[Ss]parse [Cc]ut|[Pp]ush.?[Rr]elabel",
        "slides": True,     # the lecturer teaches from the PDFs in the lecs folder
        "lecturer": None,
    },
    "cc": {
        "name": "סיבוכיות (0368-3168)",
        "folder": CC_LECS,
        "match": r"סיבוכיות|היררכי|תרגול \d+|^Lecture \d+ \d+\.\d+",   # Panopto titles like "Lecture 3 2.11"
        "slides": False,
        "lecturer": "אמיר שפילקה",
    },
}

RULES = r"""
You write Hebrew lecture notes in LyX format for Ron Goldman, a student (Tel Aviv University), from
a lecture recording: an automatic Hebrew transcript, pictures of the board/slides, and sometimes the
lecturer's slide decks.

CONTENT RULES (most important)
1. The lecture itself comes first: what was said, written on the board, or shown on the slides used in
   this lecture. Slide decks may cover more than this lecture: write only what this lecture covered.
2. No proofs the lecturer didn't give. Stated without proof -> state without proof. Left as an exercise
   -> keep as an exercise. Only an idea given -> write only the idea. No bonus theorems, corollaries or
   remarks that were not in the lecture.
3. Do fill gaps inside arguments he did give (a garbled step, a missing computation), from the slides
   or the board pictures.
4. The transcript is noisy (mis-heard words, English terms written in Hebrew letters, stray foreign
   words). Reconstruct from context. If a specific number or claim can't be recovered, say so vaguely
   in the notes rather than guessing a figure.
5. Skip administration (grading, attendance, projects, homework logistics).
6. Hebrew, clear lecture-note voice, not padded. Short intuition sentences are welcome where the
   lecturer gave intuition. Lines "[board hh:mm:ss: file]" in the transcript mark where each attached
   picture was taken; use them to line pictures up with the speech. Do not mention them in the notes.

OUTPUT FORMAT
Line 1:  OUTPUT_NAME: <name>   e.g. cc_rec3, cc_lec5, ata_lec4 (lowercase; "rec" for a recitation /
         תרגול, "lec" for a lecture; the number of the lecture/recitation; for several lectures in one
         file use a range like ata_lec1-3).
Line 2:  TITLE: <Hebrew topic title of the lecture(s)>
Then ONLY the LyX body paragraphs (no \begin_document, no header, no \begin_body / \end_body, no
Title/Author layouts, no table of contents) -- the script adds those. No ``` fences.

LyX FORMAT (LyX 2.5, Hebrew document, Ron's style)
- Layouts: Section, Subsection, Definition, Theorem, Lemma, Claim, Corollary, Remark, Example, Proof,
  Algorithm, Enumerate, Itemize, Standard. Each paragraph is
      \begin_layout <Name>
      <content>
      \end_layout
  followed by a blank line.
- A statement's name goes in an Argument inset at the start of the paragraph:
      \begin_layout Theorem
      \begin_inset Argument 1
      status open

      \begin_layout Plain Layout
      בלמן-פורד
      \end_layout

      \end_inset

      יהי
      \begin_inset Formula $G$
      \end_inset

       גרף ...
      \end_layout
- Proofs/sub-items/algorithm steps that belong to a statement go inside \begin_deeper ... \end_deeper
  placed right after that statement's \end_layout.
- Inline math: "\begin_inset Formula $...$" newline "\end_inset" newline. Display math:
  "\begin_inset Formula " newline "\[" ... "\]" newline "\end_inset".
- A Hebrew word must not run into a formula: leave a space between text and an inline formula, except
  hyphen prefixes (ב-, ל-, ש-, ה-, מ-, ו-) which stay attached: "ל-" then the formula.
- Gershayim inside a Hebrew word (מ"ט, ע"י, וכו') -> "מ" newline "\begin_inset Quotes erd" newline
  "\end_inset" newline "ט".
- English words in running text: newline "\lang english" newline word(s) newline "\lang hebrew" newline.
- IMPORTANT: two consecutive paragraphs with the same environment layout (e.g. two Definitions, two
  Theorems) at the same depth merge into ONE numbered item in LyX, even with a \begin_deeper block
  between them. Between two separate same-layout environments insert:
      \begin_layout Standard
      \begin_inset Separator plain
      \end_inset


      \end_layout
  (Several Proof paragraphs of one proof, or several Algorithm steps of one algorithm, may stay merged.)
- No macros in Section/Subsection titles (write raw TeX there, e.g. \mathsf{NL}).
- No multi-word \text{...} inside math (the words come out reversed in a Hebrew document); put words
  in the Hebrew text instead. Single-word \text{} is fine. Use \mathbf{1}, not \mathbb{1}.
- Inside math you may use the macros listed below (already defined in the document). Do not define new
  macros; write anything else in plain TeX (\mathsf{...} for complexity classes / named problems).
- Every \begin_layout/\end_layout, \begin_inset/\end_inset, \begin_deeper/\end_deeper must balance.
"""


def log(*a):
    print(*a, flush=True)


def read(p):
    return open(p, encoding="utf-8").read()


# ------------------------------------------------------------------ LyX header from Ron's own files
def header_and_macros():
    lec2 = read(HEADER_SRC).split("\n")
    first_macro = next(i for i, l in enumerate(lec2) if l == "\\begin_inset FormulaMacro")
    while lec2[first_macro] != "\\begin_layout Standard":
        first_macro -= 1
    head = lec2[:first_macro]
    body_at = head.index("\\begin_body")
    lec4 = read(MACROS_SRC).split("\n")
    m0 = next(i for i, l in enumerate(lec4) if l == "\\begin_inset FormulaMacro")
    while lec4[m0] != "\\begin_layout Standard":
        m0 -= 1
    m1 = m0
    while lec4[m1] != "\\end_layout":
        m1 += 1
    macro_par = "\n".join(lec4[m0:m1 + 1])
    names = re.findall(r"\\newcommand\{(\\[A-Za-z]+)\}(\[\d\])?", macro_par)
    return head[:body_at + 1], head[body_at + 1:], macro_par, [n + a for n, a in names]


def title_block(after_body, course, kind_word, number, topic):
    """Ron's title/author/TOC paragraphs from cc_lec2, with this course and lecture filled in."""
    txt = "\n".join(after_body)
    title = ("\\begin_layout Title\n\\paragraph_spacing double\n\n\\series bold\n\\size huge\n"
             f"{course['name']} | {kind_word} \n\\numeric on\n{number}\n\\numeric off\n\n\\series default\n"
             f"\\size default\n\\begin_inset Newline newline\n\\end_inset\n\n{topic}\n\\end_layout\n")
    author = "\\begin_layout Author\nרון גולדמן"
    if course.get("lecturer"):
        author += f"\n\\begin_inset Newline newline\n\\end_inset\n\nלפי הרצאות של {course['lecturer']}"
    author += "\n\\end_layout\n"
    txt = re.sub(r"\\begin_layout Title\n.*?\\end_layout\n", lambda m: title, txt, count=1, flags=re.S)
    txt = re.sub(r"\\begin_layout Author\n.*?\\end_layout\n", lambda m: author, txt, count=1, flags=re.S)
    return txt


# ------------------------------------------------------------------ inputs
def find_transcripts(only):
    out = []
    for f in sorted(os.listdir(TRANSCRIPTS)):
        if f.endswith("_transcript.txt") and (not only or only in f):
            stem = f[: -len("_transcript.txt")]
            frames = os.path.join(TRANSCRIPTS, stem + "_frames")
            out.append({"stem": stem, "txt": os.path.join(TRANSCRIPTS, f),
                        "frames": frames if os.path.isdir(frames) else None})
    return out


def course_of(stem, text):
    for key, c in COURSES.items():
        if re.search(c["match"], stem):
            return key
    for key, c in COURSES.items():           # fall back on the transcript's first lines
        if re.search(c["match"], text[:3000]):
            return key
    return None


def pick_frames(folder, max_frames):
    if not folder:
        return []
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if len(files) > max_frames:            # evenly spaced subset
        step = len(files) / max_frames
        files = [files[int(i * step)] for i in range(max_frames)]
    return [os.path.join(folder, f) for f in files]


def slide_pdfs(course):
    if not course["slides"] or not os.path.isdir(course["folder"]):
        return []
    # the lecturer's decks only: not notes generated from them (ata_lec1-3.pdf, cc_rec3.pdf, ...)
    return [os.path.join(course["folder"], f) for f in sorted(os.listdir(course["folder"]))
            if f.lower().endswith(".pdf") and not re.match(r"^[a-z]+_(lec|rec)\d", f)]


# ------------------------------------------------------------------ output checks
def check_body(body):
    problems = []
    for a, b in [("\\begin_layout", "\\end_layout"), ("\\begin_inset", "\\end_inset"),
                 ("\\begin_deeper", "\\end_deeper")]:
        na = len(re.findall(re.escape(a) + r"\b", body))
        nb = len(re.findall(re.escape(b) + r"\b", body))
        if na != nb:
            problems.append(f"{a} {na} vs {b} {nb}")
    for bad in ("\\begin_document", "\\begin_body", "\\end_body", "\\end_document", "\\begin_layout Title"):
        if bad in body:
            problems.append(f"contains {bad}")
    return problems


def add_missing_separators(body):
    """Insert a Separator between two same-layout environments at depth 0 (LyX would merge them)."""
    envs = {"Definition", "Theorem", "Lemma", "Claim", "Corollary", "Remark", "Example", "Exercise"}
    sep = "\\begin_layout Standard\n\\begin_inset Separator plain\n\\end_inset\n\n\n\\end_layout\n\n"
    out, last, depth = [], None, 0
    for line in body.split("\n"):
        m = re.match(r"\\begin_layout (\S+)", line)
        if line == "\\begin_deeper":
            depth += 1
        elif line == "\\end_deeper":
            depth -= 1
        elif m and depth == 0:
            if m.group(1) in envs and m.group(1) == last:
                out.append(sep.rstrip("\n"))
                out.append("")
            last = m.group(1)
        out.append(line)
    return "\n".join(out)


def compile_lyx(path):
    if not os.path.exists(LYX_EXE):
        return "LyX not found; not compiled"
    r = subprocess.run([LYX_EXE, "-batch", "--export", "pdf4", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    return "compiled" if r.returncode == 0 else "LyX errors:\n" + (r.stdout + r.stderr)[-1500:]


# ------------------------------------------------------------------ Gemini
def gemini_call(client, model, parts_text, images, pdfs):
    from google.genai import types
    contents = []
    for p in pdfs:
        f = client.files.upload(file=p)
        contents.append(f)
    for img in images:
        mime = "image/png" if img.lower().endswith(".png") else "image/jpeg"
        contents.append(types.Part.from_text(text=f"[picture {os.path.basename(img)}]"))
        contents.append(types.Part.from_bytes(data=open(img, "rb").read(), mime_type=mime))
    contents.append(parts_text)
    resp = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=65536))
    return resp.text or ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"))
    ap.add_argument("--max-frames", type=int, default=120, help="pictures per transcript (evenly spaced)")
    ap.add_argument("--combine", action="store_true", help="one notes file per course")
    ap.add_argument("--only", help="only transcripts whose file name contains this text")
    ap.add_argument("--course", choices=list(COURSES), help="force the course (with --only)")
    ap.add_argument("--force", action="store_true", help="redo transcripts already in the manifest")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, call nothing")
    ap.add_argument("--no-compile", action="store_true")
    a = ap.parse_args()

    manifest = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else {}
    head, after_body, macro_par, macro_names = header_and_macros()

    jobs = {}
    for t in find_transcripts(a.only):
        if t["stem"] in manifest and not a.force:
            log(f"skip (done before -> {manifest[t['stem']]['output']}): {t['stem']}")
            continue
        text = read(t["txt"])
        key = a.course or course_of(t["stem"], text)
        if not key:
            log(f"skip (course not recognised; use --only ... --course ...): {t['stem']}")
            continue
        t["text"] = text
        group = key if a.combine else f"{key}:{t['stem']}"
        jobs.setdefault(group, {"course": key, "items": []})["items"].append(t)

    if not jobs:
        log("Nothing to do.")
        return

    client = None
    if not a.dry_run:
        if not os.environ.get("GEMINI_API_KEY"):
            sys.exit("Set the GEMINI_API_KEY environment variable first.")
        from google import genai
        client = genai.Client()

    for group, job in jobs.items():
        course = COURSES[job["course"]]
        items = job["items"]
        per = max(10, a.max_frames // len(items))
        images = [img for t in items for img in pick_frames(t["frames"], per)]
        pdfs = slide_pdfs(course)
        chars = sum(len(t["text"]) for t in items)
        log(f"\n=== {group}: {len(items)} transcript(s), {chars:,} chars (~{chars // 3:,} tokens), "
            f"{len(images)} pictures, {len(pdfs)} slide PDF(s) -> {course['folder']}")
        for t in items:
            log(f"    {t['stem']}")
        for p in pdfs:
            log(f"    slides: {os.path.basename(p)}")
        if a.dry_run:
            continue

        prompt = RULES + "\n\nMACROS ALREADY DEFINED IN THE DOCUMENT (use them in math):\n" + \
            " ".join(macro_names) + f"\n\nCOURSE: {course['name']}\n"
        if pdfs:
            prompt += ("The attached PDFs are the lecturer's slide decks for the course; he teaches from them. "
                       "Use them for exact statements and notation, but cover only what these lecture(s) covered.\n")
        if len(items) > 1:
            prompt += "These transcripts are consecutive lectures: write ONE notes file covering all of them, " \
                      "with one Section per lecture topic, in order.\n"
        for t in items:
            prompt += f"\n\n===== TRANSCRIPT: {t['stem']} =====\n{t['text']}\n"

        log("    calling Gemini ...")
        raw = gemini_call(client, a.model, prompt, images, pdfs)
        raw = re.sub(r"^```[a-zA-Z]*\n|\n```\s*$", "", raw.strip())
        m_name = re.match(r"OUTPUT_NAME:\s*([a-z0-9_\-]+)\s*\n", raw)
        name = m_name.group(1) if m_name else re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_")
        raw = raw[m_name.end():] if m_name else raw
        m_title = re.match(r"TITLE:\s*(.+)\n", raw)
        topic = m_title.group(1).strip() if m_title else ""
        body = raw[m_title.end():] if m_title else raw
        body = add_missing_separators(body.strip() + "\n")

        nums = re.findall(r"(\d+)", name.split("_", 1)[-1])
        number = "-".join(nums[:2]) if nums else "?"
        kind_word = "תרגול" if "_rec" in name else "הרצאה"
        doc = "\n".join(head) + "\n" + title_block(after_body, course, kind_word, number, topic) + \
            "\n" + macro_par + "\n\n" + body + "\n\\end_body\n\\end_document\n"

        os.makedirs(course["folder"], exist_ok=True)
        out = os.path.join(course["folder"], name + ".lyx")
        if os.path.exists(out):
            out = os.path.join(course["folder"], name + ".gemini.lyx")
        open(out, "w", encoding="utf-8", newline="\n").write(doc)
        problems = check_body(body)
        log(f"    wrote {out}" + (f"\n    WARNING, unbalanced LyX: {problems}" if problems else ""))
        if not a.no_compile and not problems:
            log("    " + compile_lyx(out))

        for t in items:
            manifest[t["stem"]] = {"output": out, "model": a.model,
                                   "date": datetime.datetime.now().isoformat(timespec="seconds")}
        json.dump(manifest, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
