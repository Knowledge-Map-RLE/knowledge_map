"""Дословная исследовательская ревизия PDF Manly 2008 по проверенным областям страниц."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import prepare_source, require
from infrastructure.immutable_files import write_immutable

NS = '{http://www.w3.org/1999/xhtml}'
TITLE = 'Frequency and Course of Mild Cognitive Impairment in a Multiethnic Community'
VERSION = 'manly-verbatim-spatial-source-1'


def regions(page):
    # Координаты в пунктах PDF проверены по отрисованным страницам; таблицы читаются по строкам.
    if page == 1:
        return [('front', 0, 0, 594, 375, 'body'), ('left', 0, 375, 300, 646, 'body'),
                ('right', 300, 375, 594, 646, 'body'), ('metadata-left', 0, 646, 300, 740, 'body'),
                ('metadata-right', 300, 646, 594, 740, 'body')]
    if page == 6:
        return [('table1', 0, 0, 594, 280, 'body'), ('left', 0, 280, 300, 400, 'body'),
                ('right', 300, 280, 594, 400, 'body'), ('table2', 0, 400, 594, 740, 'body')]
    if page == 7:
        return [('left', 0, 0, 300, 400, 'body'), ('right', 300, 0, 594, 400, 'body'),
                ('table3', 0, 400, 594, 740, 'body')]
    if page == 8:
        return [('table4', 0, 0, 300, 330, 'body'), ('left', 0, 330, 300, 740, 'body'),
                ('right', 300, 0, 594, 740, 'body')]
    if page == 9:
        return [('table5', 0, 0, 594, 360, 'body'), ('left', 0, 360, 300, 740, 'body'),
                ('right', 300, 360, 594, 740, 'body')]
    if page == 10:
        return [('table6', 0, 0, 594, 260, 'body'), ('left', 0, 260, 300, 740, 'body'),
                ('right', 300, 260, 594, 740, 'body')]
    if page == 12:
        return [('left', 0, 0, 300, 740, 'body'), ('right-body', 300, 0, 594, 195, 'body'),
                ('right-references', 300, 195, 594, 740, 'references')]
    return [('left', 0, 0, 300, 740, 'references' if page == 13 else 'body'),
            ('right', 300, 0, 594, 740, 'references' if page == 13 else 'body')]


def extract_words(tree):
    pages = tree.findall('.//' + NS + 'page')
    require(len(pages) == 13, 'Expected thirteen original PDF pages')
    words = []
    for page_id, page in enumerate(pages, 1):
        for word in page.findall('.//' + NS + 'word'):
            words.append({'id': len(words), 'page': page_id, 'text': word.text or '',
                          'box': [float(word.attrib[k]) for k in ('xMin', 'yMin', 'xMax', 'yMax')]})
    return words


def build(pdf_path, bbox_path, intake_path, review_path):
    intake = json.loads(intake_path.read_text(encoding='utf-8'))
    pdf_hash = sha256(pdf_path.read_bytes()).hexdigest()
    require(pdf_hash == intake['pdf_sha256'] and intake['id'] == 'manly2008', 'Original PDF identity differs')
    words = extract_words(ET.parse(bbox_path))
    assignments, excluded, grouped = {}, [], []
    for page in range(1, 14):
        page_words = [w for w in words if w['page'] == page]
        for name, x0, y0, x1, y1, category in regions(page):
            chosen = []
            for word in page_words:
                a, b, c, d = word['box']
                if x0 <= (a + c) / 2 < x1 and y0 <= (b + d) / 2 < y1:
                    require(word['id'] not in assignments, 'Overlapping reading regions')
                    assignments[word['id']] = (page, name)
                    chosen.append(word)
            grouped.append({'page': page, 'region': name, 'category': category, 'words': chosen})
    for word in words:
        if word['id'] not in assignments:
            require(word['box'][1] >= 740, 'Unaccounted body word outside selected regions')
            excluded.append({**word, 'reason_ru': 'Служебный колонтитул или издательские сведения ниже тела страницы.'})

    parts, bindings = ['# ' + TITLE + '\n\n'], []
    manual = []
    def append_region(region):
        parts.append(f"## PDF page {region['page']}, region {region['region']}\n\n")
        lines = []
        for word in sorted(region['words'], key=lambda w: (w['box'][1], w['box'][0])):
            if not lines or abs(word['box'][1] - lines[-1][0]) > 2:
                lines.append((word['box'][1], [word]))
            else:
                lines[-1][1].append(word)
        for _, line in lines:
            # Табличная строка получает собственный фрагмент; порядок колонок сохранён.
            for index, word in enumerate(sorted(line, key=lambda w: w['box'][0])):
                if index:
                    parts.append(' ')
                start = sum(map(len, parts))
                parts.append(word['text'])
                bindings.append({**word, 'start': start, 'end': start + len(word['text']),
                                 'category': region['category'], 'region': region['region']})
            parts.append('\n\n' if region['region'].startswith('table') else '\n')
        parts.append('\n')
    for region in grouped:
        if region['category'] == 'body':
            append_region(region)
        if region['page'] == 2 and region['region'] == 'right':
            figure = ('Figure 1, printed diagram labels: 1992 cohort; 1999 cohort; 1992 baseline 2125; '
                      '2183 1999 baseline; 4308 potential participants; 478 insufficient data to diagnose MCI at all visits; '
                      '3830 remaining; 615 demented at first visit with complete data; 3215 remaining; '
                      '785 no follow-up data; 2430 remaining; 66 insufficient data to diagnose MCI or dementia at follow-up; '
                      '2364 remaining. MCI = mild cognitive impairment.')
            start = sum(map(len, parts))
            parts.append('### Figure 1: labels transcribed from the original image\n\n' + figure + '\n\n')
            manual.append({'page': 2, 'kind': 'figure_label_transcription', 'text': figure,
                           'start': start + len('### Figure 1: labels transcribed from the original image\n\n'),
                           'end': sum(map(len, parts)) - 2,
                           'render_sha256': sha256((review_path / 'pdf-page-02.png').read_bytes()).hexdigest(),
                           'scientific_curve_values_digitized': False, 'author': 'Codex'})
    parts.append('# References\n\n')
    for region in grouped:
        if region['category'] == 'references':
            append_region(region)
    text = ''.join(parts)
    require(all(text[w['start']:w['end']] == w['text'] for w in bindings), 'Source-to-PDF word binding differs')
    require(len(bindings) + len(excluded) == len(words), 'PDF word conservation failed')
    require(all(text[m['start']:m['end']] == m['text'] for m in manual), 'Manual figure text binding differs')
    source = prepare_source('manly2008-complete', text)
    require(source['references_excluded'], 'Explicit bibliography boundary required')
    require(all(w['end'] <= source['content_end'] for w in bindings if w['category'] == 'body'), 'Body leaked into bibliography')
    require(all(w['start'] >= source['content_end'] for w in bindings if w['category'] == 'references'), 'Bibliography leaked into body')
    proof = {'version': VERSION, 'pdf_sha256': pdf_hash,
             'bbox_sha256': sha256(bbox_path.read_bytes()).hexdigest(), 'source_sha256': source['sha256'],
             'pdf_word_count': len(words), 'retained_word_count': len(bindings),
             'excluded_footer_word_count': len(excluded), 'words': bindings, 'excluded_words': excluded,
             'manual_transcriptions': manual, 'coordinate_unit': 'PDF points; source offsets Unicode code points',
             'summarized_source_paragraphs': 0, 'complete_map_created': False,
             'model_calls': 0, 'expert_validated': False}
    return text, source, proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    old = root / 'eval/free_prediction/primary-pdf-cohort-v1/sources/manly2008'
    target = root / 'eval/whole_map_forecast/manly-complete-map-v1/source-v1'
    review = target.parent / 'source-review'
    text, source, proof = build(old / 'article.pdf', review / 'original.bbox.html', old / 'intake.json', review)
    for name, value in {'source.en.md': text, 'source.json': source, 'pdf-word-provenance.json': proof}.items():
        data = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        write_immutable(target / name, data)
    print(json.dumps({k: proof[k] for k in ('source_sha256', 'pdf_word_count', 'retained_word_count', 'excluded_footer_word_count')}, indent=2))
    print('source_units:', len(source['units']))


if __name__ == '__main__':
    main()
