"""Per-lecture PDFs for the site's "by lecture" option: each lecture is its own complete document
(own title page and table of contents), never pages cut out of the united PDF.

    py website/split_lectures.py          (run from the repo root, before committing)

For every entry in website/pdf_data.json with "by_lecture", the standalone lecture PDFs are copied
into summaries/<dir>/by_lecture/<n>.pdf and the entry's "lectures" list is rewritten. Sources:
    "by_lecture": {"parts": "C:/.../<stem>_parts/parts.json"}
        made by the notes tool:  make_notes.py --split-out <notes.tex> --label Lecture
        (every section of the notes becomes its own compiled document)
    "by_lecture": {"pdfs": [{"title": "...", "from": "C:/.../lec1.pdf"}, ...]}
        lecture PDFs that already exist (e.g. hand-made per-lecture notes)
Sources outside the repo are only read; nothing is cropped.

    "URL_from": "C:/.../<stem>.pdf"   the course's main (united / merged) PDF: copied to "URL".

Only APPROVED notes reach the site: a source whose .tex next to it is still a draft (the notes
tool's %%NOTES-DRAFT-BEGIN box) is skipped, and the site keeps the copy it already has.
"""
import json, os, shutil, sys

DATA = os.path.join('website', 'pdf_data.json')
DRAFT = '%%NOTES-DRAFT-BEGIN'


def is_draft(pdf):
    tex = os.path.splitext(pdf)[0] + '.tex'
    try:
        return DRAFT in open(tex, encoding='utf-8').read()
    except OSError:
        return False  # hand-made PDFs have no .tex next to them


def sync(src, dst):
    """Copy an approved source; returns False when the site keeps its older copy (draft or missing)."""
    if not os.path.isfile(src):
        print('  missing (kept the site copy): %s' % src)
        return False
    if is_draft(src):
        print('  draft, not approved yet (kept the site copy): %s' % src)
        return False
    if not (os.path.isfile(dst) and open(src, 'rb').read() == open(dst, 'rb').read()):
        shutil.copyfile(src, dst)
        print('  %s  <-  %s' % (dst, src))
    return True


def sources(opts):
    if 'parts' in opts:
        parts = json.load(open(opts['parts'], encoding='utf-8'))
        return [(p['title'], p['pdf']) for p in parts]
    if 'pdfs' in opts:
        return [(p['title'], p['from']) for p in opts['pdfs']]
    sys.exit('by_lecture needs "parts" or "pdfs" (cropping the united PDF is no longer done)')


def build(entry):
    srcs = sources(entry['by_lecture'])
    outdir = os.path.join(os.path.dirname(entry['URL']), 'by_lecture')
    os.makedirs(outdir, exist_ok=True)
    lectures = []
    for i, (title, src) in enumerate(srcs, 1):
        dst = os.path.join(outdir, '%d.pdf' % i)
        if sync(src, dst) or os.path.isfile(dst):  # a draft with no older copy is left out for now
            lectures.append({'title': title, 'URL': dst.replace(os.sep, '/')})
    for f in os.listdir(outdir):  # files from an older, longer list
        if f.endswith('.pdf') and f[:-4].isdigit() and int(f[:-4]) > len(srcs):
            os.remove(os.path.join(outdir, f))
    entry['lectures'] = lectures


def main():
    data = json.load(open(DATA, encoding='utf-8'))
    for key, entry in data.items():
        if entry.get('URL_from'):
            print(key)
            os.makedirs(os.path.dirname(entry['URL']), exist_ok=True)
            sync(entry['URL_from'], entry['URL'])
        if entry.get('by_lecture'):
            print(key)
            build(entry)
    with open(DATA, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write('\n')


if __name__ == '__main__':
    main()
