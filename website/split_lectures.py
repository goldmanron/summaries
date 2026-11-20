"""Split merged summaries into per-lecture PDFs for the site's "by lecture" option.

    py website/split_lectures.py          (run from the repo root, before committing)

For every entry in website/pdf_data.json with "by_lecture", the merged PDF (its "URL") is cut
at its top-level bookmarks (one per lecture / chapter) into
summaries/<dir>/by_lecture/<n>.pdf, and the entry's "lectures" list is rewritten:
    "by_lecture": {"label": "הרצאה"}   -> items "הרצאה 1: <bookmark title>", ...
    "by_lecture": {"label": ""}        -> items "<bookmark title>"
    "by_lecture": {..., "source": "summaries/x/y.pdf"} -> split that PDF instead of "URL"
A lecture that starts mid-page keeps that page in the previous lecture's PDF too, so no text
is cut off at a boundary.
An entry may instead list its lecture PDFs by hand ("lectures": [{"title": ..., "URL": ...}])
without "by_lecture"; those are left alone. The site builder shows a "by lecture" button for
every entry that has a non-empty "lectures" list.
"""
import json, os, sys
from pypdf import PdfReader, PdfWriter

DATA = os.path.join('website', 'pdf_data.json')


def top_level(reader):
    out = []
    for item in reader.outline:
        if isinstance(item, list):
            continue
        page = reader.get_destination_page_number(item)
        height = float(reader.pages[page].mediabox.height)
        top = getattr(item, 'top', None)
        # starts at the top of its page (a chapter / new page)? then the previous part ends before it
        at_top = top is None or float(top) >= height - 150
        out.append((item.title.strip(), page, at_top))
    return out


def split(entry):
    opts = entry['by_lecture'] if isinstance(entry['by_lecture'], dict) else {}
    src = opts.get('source', entry['URL'])  # a lecture-ordered version, if the main PDF is not
    reader = PdfReader(src)
    marks = top_level(reader)
    if not marks:
        sys.exit('%s has no top-level bookmarks to split at' % src)
    label = opts.get('label', 'הרצאה')
    outdir = os.path.join(os.path.dirname(src), 'by_lecture')
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):  # drop parts from an older split
        if f.endswith('.pdf'):
            os.remove(os.path.join(outdir, f))
    lectures = []
    for i, (title, start, _) in enumerate(marks):
        if i + 1 < len(marks):
            nxt, nxt_top = marks[i + 1][1], marks[i + 1][2]
            end = nxt if nxt_top else nxt + 1  # share the page the next lecture starts on
        else:
            end = len(reader.pages)
        w = PdfWriter()
        for p in range(start, max(end, start + 1)):
            w.add_page(reader.pages[p])
        w.add_metadata({'/Title': title, '/Author': 'Ron Goldman'})
        path = os.path.join(outdir, '%d.pdf' % (i + 1))
        with open(path, 'wb') as fh:
            w.write(fh)
        lectures.append({'title': ('%s %d: %s' % (label, i + 1, title)) if label else title,
                         'URL': path.replace(os.sep, '/')})
        print('  %s  pages %d-%d  %s' % (path, start + 1, max(end, start + 1), title))
    entry['lectures'] = lectures


def main():
    data = json.load(open(DATA, encoding='utf-8'))
    for key, entry in data.items():
        if entry.get('by_lecture'):
            print(key)
            split(entry)
    with open(DATA, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write('\n')


if __name__ == '__main__':
    main()
