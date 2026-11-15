import json

from services.ai_service import AIService, SYSTEM_PROMPT
from services.semantic_service import SemanticIndex
from config import Config


def test_profiles_are_cached_and_invalidated_on_csv_changes(csv_service, data_dir, monkeypatch):
    original = csv_service._load_uncached
    calls=[]
    def load(id):
        calls.append(id)
        return original(id)
    monkeypatch.setattr(csv_service,'_load_uncached',load)
    first, df = csv_service.load('flame_spread')
    first['name']='changed by caller'
    df.iloc[0,0]='changed by caller'
    second, df2=csv_service.load('flame_spread')
    assert calls == ['flame_spread']
    assert second['name'] == 'TestFlame' and df2.iloc[0,0] == 'TestFlame'
    path=data_dir/'flame_spread.csv'
    path.write_text(path.read_text().replace('1.2','9.2'))
    _,df3=csv_service.load('flame_spread')
    assert len(calls)==2 and df3.loc[1,'Flame_Spread_mm_s']=='9.2'


def test_metadata_updates_invalidate_profile_cache(csv_service, data_dir):
    csv_service.load('flame_spread')
    (data_dir/'flame_spread.json').write_text(json.dumps(dict(name='Updated title',metadata={},chunk_count=0,source_references=[])))
    assert csv_service.build_profile('flame_spread')['name']=='Updated title'


def test_short_output_policy_and_compact_history(research, fake_ai):
    assert '80–140 words' in SYSTEM_PROMPT
    assert 'Expand only when the user explicitly asks for detail' in SYSTEM_PROMPT
    history=[dict(role='assistant',content=str(i)+'x'*5000) for i in range(12)]
    compact=research._history(history)
    assert len(compact)==6 and all(len(m['content'])<=1500 for m in compact)
    result=research.ask('Explain smoke detector results',history)
    assert result['timing_ms']['retrieval']>=0 and result['timing_ms']['generation']>=0


def test_query_embeddings_are_reused_and_failures_back_off(tmp_path, monkeypatch):
    (tmp_path/'demo.chunks.json').write_text(json.dumps([dict(id='c',kind='report',text='flame spread')]))
    index=SemanticIndex(Config(env={},DATA_DIR=tmp_path,RAG_INDEX_PATH=tmp_path/'index.sqlite'))
    monkeypatch.setattr(index,'embed',lambda texts:[[1.0,0.0] for _ in texts])
    index.build()
    calls=[]
    def embed(texts):
        calls.append(texts)
        return [[1.0,0.0]]
    monkeypatch.setattr(index,'embed',embed)
    assert index.search('flame')==index.search('flame')=={'c':1.0}
    assert len(calls)==1
    def offline(texts):
        calls.append(texts)
        raise RuntimeError('offline')
    monkeypatch.setattr(index,'embed',offline)
    assert index.search('new query')=={}
    assert index.search('another query')=={}
    assert len(calls)==2


def test_openai_reasoning_setting_is_sent(monkeypatch):
    seen={}
    class Response:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':'Brief response.'}}]}
    def post(url,**kwargs):
        seen.update(kwargs['json'])
        return Response()
    monkeypatch.setattr('services.ai_service.requests.post',post)
    service=AIService(Config(env={'AI_PROVIDER':'openai','AI_MODEL':'gpt-5-mini','OPENAI_API_KEY':'test','AI_REASONING_EFFORT':'low'}))
    service.generate('Answer briefly','Evidence')
    assert seen['reasoning_effort']=='low'
