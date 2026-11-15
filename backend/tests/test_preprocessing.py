import json
from pathlib import Path

from preprocess import preprocess
from services.csv_service import CsvService
from services.research_service import ResearchService
from config import Config


def test_saved_metadata_and_chunks_feed_api_and_retrieval(tmp_path, fake_ai):
    source = tmp_path / 'sources' / 'PSI-test'
    (source / 'experiments').mkdir(parents=True)
    (source / 'metadata.txt').write_text('Study Title\tSynthetic study\nComment[Objective]\t"Study suppression\nwith nitrogen"\n')
    (source / 'experiments/table.csv').write_text('Material,O2_pct\nAlpha,21\n')
    output = tmp_path / 'processed'
    preprocess(source, output)
    config = Config(env={}, DATA_DIR=output)
    csv = CsvService(config)
    profile = csv.get_investigation('PSI-test')
    assert profile['name'] == 'Synthetic study'
    assert profile['row_count'] == 1
    assert profile['conditions']['objective']['values'] == ['Study suppression\nwith nitrogen']
    research = ResearchService(config, csv, fake_ai)
    result = research.ask('How does nitrogen suppression work?')
    assert any(r['type'] == 'chunk' for r in result['references'])
    assert 'nitrogen' in fake_ai.calls[-1]['context']
    assert research.check_citations('[E1:C1]', {'E1:C1'})['all_citations_valid']
    csv.delete_investigation('PSI-test')
    assert not list(output.glob('*.json'))


def test_pdf_only_terms_are_retrieved_in_questions_and_insights(tmp_path, fake_ai):
    output = tmp_path / 'processed'
    output.mkdir()
    (output / 'demo.csv').write_text('Material,O2_pct\nAlpha,21\n')
    chunks = [dict(id='report-only', investigation_id='demo', kind='report',
                   file='demo/report.pdf', page=7, offset=0,
                   text='Conclusions: Spectroscopic smoke detection revealed quenching hysteresis.')]
    (output / 'demo.chunks.json').write_text(json.dumps(chunks))
    config = Config(env={}, DATA_DIR=output)
    research = ResearchService(config, CsvService(config), fake_ai)
    for result in (research.ask('What spectroscopic hysteresis was observed?'),
                   research.summarize('demo'), research.insights('smoke_detection')):
        assert result['answerable']
        ref = next(r for r in result['references'] if r['type'] == 'chunk')
        assert ref['page'] == 7 and ref['id'] == 'report-only'
    assert all('quenching hysteresis' in c['context'] for c in fake_ai.calls)


def test_truncation_references_only_include_supplied_evidence(tmp_path, fake_ai):
    output = tmp_path / 'processed'
    output.mkdir()
    (output / 'demo.csv').write_text('Material,O2_pct\nAlpha,21\n')
    config = Config(env={}, DATA_DIR=output, MAX_CONTEXT_CHARS=80)
    research = ResearchService(config, CsvService(config), fake_ai)
    entries = research._retrieve(['alpha'], [])
    context, truncated = research._build_context(entries)
    assert truncated and len(context) <= 80
    assert research._references(entries) == []


def test_real_report_conclusions_have_page_provenance():
    artifact = Path(__file__).resolve().parents[1] / 'data/experiments/PSI-25.json'
    profile = json.loads(artifact.read_text())
    assert len(profile['findings']) >= 1
    assert all(f['page'] > 1 and len(f['text']) > 100 for f in profile['findings'])
    assert any('two-sided' in f['text'] for f in profile['findings'])


def test_real_findings_query_prioritizes_conclusions_over_contents():
    output = Path(__file__).resolve().parents[1] / 'data/experiments'
    config = Config(env={}, DATA_DIR=output)
    research = ResearchService(config, CsvService(config), None)
    words, numbers = research._question_terms('What are the findings of PSI-25?')
    entry = research._retrieve(words, numbers)[0]
    assert entry['chunks'][0]['section'] == 'Conclusions'
    assert entry['chunks'][0]['page'] > 5
    words, numbers = research._question_terms('What did BASS-II conclude about one-sided and two-sided burns?')
    entry = research._retrieve(words, numbers)[0]
    assert entry['chunks'][0]['page'] == 71


def test_flex_package_is_available_with_all_documents_and_plan(fake_ai):
    from app import create_app
    from services.chart_service import build_chart
    output = Path(__file__).resolve().parents[1] / 'data/experiments'
    config = Config(env={}, DATA_DIR=output)
    csv = CsvService(config)
    profile, df = csv.load('PSI-69')
    assert profile['name'] == 'Flame Extinguishment Experiment'
    assert profile['row_count'] == 274
    assert len(profile['documents']) == 4
    assert {d['kind'] for d in profile['documents']} == {'presentation', 'report'}
    assert 'FLEX – Calibration' in profile['metadata']['Comment[Test Plan]'][0]
    oxygen = profile['conditions']['oxygen']
    assert oxygen['unit'] == 'fraction'
    assert oxygen['normalized']['min'] == 12
    assert oxygen['normalized']['max'] == 34
    assert profile['conditions']['pressure']['unit'] == 'mmhg'
    assert 'FLEX Test #' not in profile['measurements']
    assert df.loc[1, 'O initial ambient composition; mole fraction'] == '0.21'
    chart = build_chart({'type': 'scatter', 'x': oxygen['column'], 'y': 'Burning rate; mm'}, profile, df)
    assert chart['points'][0]['x'] == 0.21
    assert chart['points'][0]['y'] == 0.52
    assert any(f['page'] == 10 and '2G11' in f['file'] for f in profile['findings'])
    research = ResearchService(config, csv, fake_ai)
    chunks = research._load_chunks('PSI-69')
    assert {d['file'] for d in profile['documents']} <= {c['file'] for c in chunks}
    assert any(c.get('field') == 'Comment[Test Plan]' for c in chunks)
    result = research.ask('What water flux transition point is described by the LLUV camera presentation?')
    assert any(r.get('file') == 'PSI-69/presentations/20130010979.pdf' for r in result['references'])
    client = create_app(config).test_client()
    response = client.get('/api/investigations/PSI-69?include_records=true').get_json()
    assert response['success'] and response['data']['records_total'] == 274
    items = client.get('/api/investigations').get_json()['data']
    assert {i['id'] for i in items} >= {'PSI-25', 'PSI-69'}


def test_saffire_samples_notes_context_and_charts(fake_ai):
    from services.chart_service import build_chart
    from app import create_app
    config = Config(env={}, DATA_DIR=Path(__file__).resolve().parents[1] / 'data/experiments')
    csv = CsvService(config)
    p, df = csv.load('PSI-99')
    assert p['row_count'] == 9
    assert len(p['table_notes']) == 6  # Two auxiliary records and four explanatory notes.
    assert len(p['documents']) == 3
    assert all(d['kind'] == 'context' for d in p['documents'])
    assert all(f.get('row_number') for f in p['findings'])
    assert df.loc[6, 'Material'] is None and df.loc[9, 'Material'] is None
    assert df.loc[4, 'Samle Thickness'] == '037 mm'
    assert any('CO2 production' in note['text'] for note in p['table_notes'])
    chart = build_chart({'type': 'bar', 'x': 'Sample Number', 'y': 'Burn Time (s)'}, p, df)
    assert chart['skipped_rows'] == 4
    assert len(chart['points']) == 5
    assert chart['points'][0]['x'] == '2-5' and chart['points'][0]['y'] == 145
    import pytest
    from services.csv_service import InvalidRequest
    with pytest.raises(InvalidRequest, match='mixes units'):
        build_chart({'type': 'bar', 'x': 'Sample Number', 'y': 'Samle Thickness'}, p, df)
    research = ResearchService(config, csv, fake_ai)
    chunks = research._load_chunks('PSI-99')
    assert any(c.get('paragraph') and c['file'].endswith('.docx') for c in chunks)
    assert any(c.get('figure') and 'S9: Flat PMMA' in c['text'] for c in chunks)
    entries = research._retrieve(*research._question_terms('Explain the airflow discrepancy for S6 and S9'), only_ids=['PSI-99'])
    context, _ = research._build_context(entries)
    assert 'discrepancy' in context and '30 cm/s' in context
    assert 'not a final results report' in context or any(d.get('role') for d in p['documents'])
    client = create_app(config).test_client()
    response = client.get('/api/investigations/PSI-99?include_records=true').get_json()
    assert response['data']['records_total'] == 9
    assert len(client.get('/api/investigations').get_json()['data']) == 3
