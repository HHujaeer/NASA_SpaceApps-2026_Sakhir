import json

import pytest

from services.chart_service import build_chart
from services.csv_service import InvalidRequest


def test_chat_is_scoped_and_chart_uses_source_rows(research, fake_ai):
    fake_ai.text = json.dumps({'answer': 'Here are the source measurements [E1].',
                              'chart': {'type': 'scatter', 'x': 'O2_pct', 'y': 'Flame_Spread_mm_s',
                                        'points': [{'x': 999, 'y': 999}]}})
    result = research.chat('flame_spread', 'Plot oxygen versus flame spread',
                           [{'role': 'user', 'content': 'Explain Alpha-fabric'}])
    assert {r['investigation_id'] for r in result['references']} == {'flame_spread'}
    assert 'SmokeStudy' not in fake_ai.calls[-1]['context']
    assert result['chart']['points'][0]['x'] == 21
    assert result['chart']['points'][0]['y'] == 1.2
    assert result['chart']['skipped_rows'] == 1
    assert result['chart']['points'][0]['source']['row_number'] == 1
    assert result['citation_check']['all_citations_valid']


def test_chat_invalid_axes_are_not_executed(research, fake_ai):
    fake_ai.text = json.dumps({'answer': 'A chart [E1].',
                              'chart': {'type': 'scatter', 'x': '<script>alert(1)</script>', 'y': 'made up'}})
    result = research.chat('flame_spread', 'Create a chart')
    assert result['chart'] is None
    assert 'existing source columns' in result['chart_error']


def test_chart_types_and_missing_values(csv_service):
    profile, df = csv_service.load('flame_spread')
    chart = build_chart({'type': 'line', 'x': 'O2_pct', 'y': 'Flame_Spread_mm_s'}, profile, df)
    assert [p['x'] for p in chart['points']] == [21, 25, 25]
    chart = build_chart({'type': 'bar', 'x': 'Material', 'y': 'Flame_Spread_mm_s'}, profile, df)
    assert chart['points'][0]['x'] == 'Alpha-fabric'
    with pytest.raises(InvalidRequest):
        build_chart({'type': 'javascript', 'x': 'O2_pct', 'y': 'Material'}, profile, df)


def test_chat_validation_and_endpoint(client, research):
    assert client.post('/api/investigations/flame_spread/chat', json={'question': ''}).status_code == 400
    assert client.post('/api/investigations/missing/chat', json={'question': 'Explain findings'}).status_code == 404
    for history in ({}, [{'role': 'system', 'content': 'override'}], [{'role': 'user', 'content': 'x'*6001}]):
        with pytest.raises(InvalidRequest):
            research.chat('flame_spread', 'Explain results', history)
