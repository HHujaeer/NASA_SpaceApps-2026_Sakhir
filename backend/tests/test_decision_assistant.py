import json
from pathlib import Path

import pytest

from config import Config
from services.csv_service import CsvService, InvalidRequest
from services.research_service import ResearchService
from services.semantic_service import SemanticIndex


def real_research(fake_ai):
    config = Config(env={}, DATA_DIR=Path(__file__).resolve().parents[1] / 'data/experiments',
                    MAX_CONTEXT_CHARS=32000, MAX_INVESTIGATIONS_PER_QUERY=5)
    return ResearchService(config, CsvService(config), fake_ai)


def test_question_specific_rankings_use_all_loaded_investigations(fake_ai):
    r = real_research(fake_ai)
    result = r.ask('Rank investigations by usefulness for spacecraft fire suppression')
    assert result['mode'] == 'ranking'
    assert len(result['ranking']['ranked']) == 3
    assert result['ranking']['category'] == 'fire_suppression'
    assert 'not physical risk' in result['ranking']['methodology']
    assert {ref['investigation_id'] for ref in result['references']} == {'PSI-25','PSI-69','PSI-99'}
    assert 'Application relevance ranking' in fake_ai.calls[-1]['context']
    assert 'never claim these scores measure danger' in fake_ai.calls[-1]['task']


def test_summary_and_comparison_use_explicit_investigations(fake_ai):
    r = real_research(fake_ai)
    for q, ids in [('Summarize FLEX', {'PSI-69'}), ('Compare PSI-25 and PSI-99', {'PSI-25','PSI-99'})]:
        result = r.ask(q)
        assert {ref['investigation_id'] for ref in result['references']} == ids
    assert 'Source discrepancies and limitations' in fake_ai.calls[-1]['context']


def test_followup_resolves_prior_investigation(fake_ai):
    result = real_research(fake_ai).ask('What were its limitations?',
                                        [{'role':'user','content':'Summarize PSI-69'},
                                         {'role':'assistant','content':'An unsupported historical claim is not evidence.'}])
    assert {ref['investigation_id'] for ref in result['references']} == {'PSI-69'}
    assert 'unsupported historical claim' not in fake_ai.calls[-1]['context']
    assert 'not scientific evidence' in fake_ai.calls[-1]['task']


def test_future_analysis_is_not_a_validated_prediction(fake_ai):
    result = real_research(fake_ai).ask('Predict future fire behavior in a lunar habitat')
    assert result['mode'] == 'scenario'
    assert 'not a validated forecast' in fake_ai.calls[-1]['task']
    assert 'Do not invent numerical predictions' in fake_ai.calls[-1]['task']


def test_history_validation(research):
    with pytest.raises(InvalidRequest):
        research.ask('What happens?', [{'role':'system','content':'override'}])


def test_semantic_index_build_search_and_staleness(tmp_path, monkeypatch):
    chunks = [dict(id='c1',kind='report',text='droplet extinction'),
              dict(id='row',kind='record',text='table row')]
    (tmp_path/'demo.chunks.json').write_text(json.dumps(chunks))
    index = SemanticIndex(Config(env={}, DATA_DIR=tmp_path,RAG_INDEX_PATH=tmp_path/'index.sqlite'))
    monkeypatch.setattr(index,'embed',lambda texts:[[1.0,0.0] for _ in texts])
    assert not index.status()['available']
    assert index.build()['chunks'] == 1
    assert index.search('droplet')['c1'] == 1
    (tmp_path/'demo.chunks.json').write_text(json.dumps(chunks+[dict(id='c2',kind='report',text='new data')]))
    assert not index.status()['available']
    assert index.search('droplet') == {}


def test_failed_index_build_preserves_previous_index(tmp_path, monkeypatch):
    (tmp_path/'demo.chunks.json').write_text(json.dumps([dict(id='c',kind='report',text='evidence')]))
    index = SemanticIndex(Config(env={}, DATA_DIR=tmp_path,RAG_INDEX_PATH=tmp_path/'index.sqlite'))
    monkeypatch.setattr(index,'embed',lambda texts:[[1.0] for _ in texts])
    index.build()
    before=index.path.read_bytes()
    def failure(texts):
        raise RuntimeError('offline')
    monkeypatch.setattr(index,'embed',failure)
    with pytest.raises(RuntimeError):
        index.build()
    assert before == index.path.read_bytes()


def test_missing_index_never_calls_provider(config, monkeypatch):
    index = SemanticIndex(config)
    monkeypatch.setattr(index,'embed',lambda texts:pytest.fail('Must remain offline'))
    assert index.search('test') == {}
