"""Build local CSV profiles and provenance-bearing RAG chunks from data/<id>/."""
import argparse
import csv
import io
import hashlib
import re
import json
from pathlib import Path
import subprocess
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def metadata_fields(path):
    # ISA values may span lines; appended test-plan prose is not an ISA row.
    text = path.read_text(encoding='utf-8-sig')
    isa, marker, plan = text.partition('ADDED INFO FROM TEST PLAN:')
    fields = {row[0]: [v.strip() for v in row[1:] if v.strip()]
              for row in csv.reader(io.StringIO(isa), delimiter='\t') if row}
    if marker and plan.strip():
        fields['Comment[Test Plan]'] = [plan.strip()]
    return fields



def preprocess(source, output):
    inv_id = source.name
    fields = metadata_fields(source / 'metadata.txt')
    chunks = []
    manifest_path = source / 'sources.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    roles = manifest.get('roles', {})

    def add(text, kind, file, **location):
        if not text.strip():
            return
        key = json.dumps([inv_id, file, location, text], sort_keys=True)
        chunks.append(dict(id=hashlib.sha256(key.encode()).hexdigest()[:20],
                           investigation_id=inv_id, kind=kind, file=f'{inv_id}/{file}',
                           text=text, **location))

    for label, values in fields.items():
        if values:
            add(label + ': ' + '; '.join(values), 'metadata', 'metadata.txt', field=label)
    tables = sorted((source / 'experiments').glob('*.csv'))
    rows, columns, table_notes = [], None, []
    for table in tables:
        try:
            table_text = table.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            table_text = table.read_text(encoding='cp1252')
        with io.StringIO(table_text, newline='') as stream:
            reader = csv.DictReader(stream)
            if columns is None:
                columns = reader.fieldnames
            if reader.fieldnames != columns:
                raise ValueError(f'{table}: different table schemas require an explicit mapping')
            for n, row in enumerate(reader, 1):
                if None in row:
                    raise ValueError(f'{table}: malformed row {n}')
                if manifest.get('sample_id_pattern') and not re.fullmatch(manifest['sample_id_pattern'], row[columns[0]]):
                    note = '; '.join(f'{k}={v}' for k, v in row.items() if v)
                    if note:
                        table_notes.append(dict(text=note, file=f'{inv_id}/experiments/{table.name}', row_number=n))
                        add(note, 'context', f'experiments/{table.name}', row_number=n,
                            evidence_role='CSV note or auxiliary record, not an experiment sample')
                    continue
                rows.append(row)
                add('; '.join(f'{k}={v}' for k, v in row.items() if v), 'record',
                    f'experiments/{table.name}', row_number=n)
    if not rows:
        raise ValueError(f'{source}: no experiment records')
    findings, documents = [], []
    for note in manifest.get('data_notes', []):
        add(note, 'context', 'sources.json', field='Data limitations and source discrepancies')
    for item in manifest.get('figure_transcriptions', []):
        add(item['text'], 'context', item['file'], figure=item['figure'], evidence_role=roles.get(item['file']))
    for table in sorted((source / 'reports').glob('*.docx')):
        relative = table.relative_to(source).as_posix()
        with zipfile.ZipFile(table) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs = [''.join(node.text or '' for node in para.findall('.//w:t', ns))
                      for para in root.findall('.//w:p', ns)]
        documents.append(dict(file=f'{inv_id}/{relative}', kind='context',
                              role=roles.get(relative, 'Document reference'), paragraphs=len(paragraphs)))
        for n, text in enumerate(paragraphs, 1):
            for offset in range(0, len(text), 1400):
                add(text[offset:offset+1800], 'context', relative, paragraph=n, offset=offset,
                    evidence_role=roles.get(relative, 'Document reference'))
    for n in manifest.get('finding_rows', []):
        row = rows[n-1]
        text = '; '.join(f'{c}={row[c]}' for c in manifest['finding_columns'] if row.get(c))
        findings.append(dict(text=text, file=f'{inv_id}/experiments/{tables[0].name}', row_number=n,
                             basis='Selected experiment table observation (source wording)'))
    pdfs = sorted(set(source.glob('*.pdf')) | set((source / 'reports').glob('*.pdf'))
                  | set((source / 'presentations').glob('*.pdf')))
    heading_pattern = re.compile(
        r'^\s*(?:\d+(?:\.\d+)*\.?\s+)?(Conclusions?|Concluding Remarks|Summary)\s*$', re.M | re.I)
    stop_pattern = re.compile(
        r'^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:Acknowledg\w*|References|Future work)\s*$', re.M | re.I)
    for pdf in pdfs:
        relative = pdf.relative_to(source).as_posix()
        kind = 'context' if manifest.get('context_only') else ('presentation' if relative.startswith('presentations/') else 'report')
        result = subprocess.run(['pdftotext', '-layout', str(pdf), '-'],
                                check=True, capture_output=True)
        pages = result.stdout.decode('utf-8').split('\f')
        if not pages[-1].strip():
            pages.pop()
        documents.append(dict(file=f'{inv_id}/{relative}', kind=kind, role=roles.get(relative, kind.title()), pages=len(pages)))
        active_section = None
        for page, text in enumerate(pages, 1):
            heading = heading_pattern.search(text) if kind != 'context' else None
            if heading and kind == 'report' and heading.group(1).lower() == 'summary':
                heading = None
            if heading:
                active_section = heading.group(1)
            if heading or active_section:
                start = heading.end() if heading else 0
                excerpt = text[start:]
                stop = stop_pattern.search(excerpt)
                next_section = re.search(r'^\s*\d+(?:\.\d+)+\s+[A-Z][^\n]*$', excerpt, re.M)
                if next_section and (not stop or next_section.start() < stop.start()):
                    stop = next_section
                if stop:
                    excerpt = excerpt[:stop.start()]
                excerpt = re.split(r'\n\s*NASA/TM', excerpt, maxsplit=1)[0]
                excerpt = re.sub(r'^\s*\d+\s*$', '', excerpt, flags=re.M).strip()
                if len(excerpt) > 100:
                    section = 'Conclusions' if kind == 'report' else 'Summary'
                    add(excerpt, kind, relative, page=page, offset=start, section=section)
                    findings.append(dict(text=excerpt, file=f'{inv_id}/{relative}', page=page,
                                         basis=f'Verbatim {kind} {active_section.lower()} excerpt'))
                # Slides do not carry a section onto the next slide.
                if stop or kind == 'presentation':
                    active_section = None
            for start in range(0, len(text), 1400):
                add(text[start:start + 1800], kind, relative, page=page, offset=start, evidence_role=roles.get(relative, kind))
    output.mkdir(parents=True, exist_ok=True)
    def first(key):
        return next(iter(fields.get(key, [])), None)
    profile = dict(id=inv_id, name=first('Study Title') or inv_id, metadata=fields, findings=findings, documents=documents, data_notes=manifest.get("data_notes", []), table_notes=table_notes,
                   source_references=fields.get('Comment[DOI]', []), chunk_count=len(chunks))
    with (output / f'{inv_id}.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    (output / f'{inv_id}.json').write_text(json.dumps(profile, indent=2), encoding='utf-8')
    (output / f'{inv_id}.chunks.json').write_text(json.dumps(chunks, indent=2), encoding='utf-8')
    return dict(id=inv_id, records=len(rows), chunks=len(chunks))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data')
    parser.add_argument('--output', type=Path, default=ROOT / 'backend/data/experiments')
    args = parser.parse_args()
    for source in sorted(args.source.iterdir()):
        if source.is_dir() and (source / 'metadata.txt').exists():
            print(json.dumps(preprocess(source, args.output)))
