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
"""
import json, os, shutil, sys

DATA = os.path.join('website', 'pdf_data.json')


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
    for f in os.listdir(outdir):  # drop files from an older build
        if f.endswith('.pdf'):
            os.remove(os.path.join(outdir, f))
    lectures = []
    for i, (title, src) in enumerate(srcs, 1):
        if not os.path.isfile(src):
            sys.exit('missing lecture PDF: %s' % src)
        dst = os.path.join(outdir, '%d.pdf' % i)
        shutil.copyfile(src, dst)
        lectures.append({'title': title, 'URL': dst.replace(os.sep, '/')})
        print('  %s  <-  %s' % (dst, src))
    entry['lectures'] = lectures


def main():
    data = json.load(open(DATA, encoding='utf-8'))
    for key, entry in data.items():
        if entry.get('by_lecture'):
            print(key)
            build(entry)
    with open(DATA, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write('\n')


if __name__ == '__main__':
    main()
