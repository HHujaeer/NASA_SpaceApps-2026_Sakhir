"""Optional local embedding index. Keyword retrieval remains available offline."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from functools import lru_cache
from time import monotonic

import requests


class SemanticIndex:
    def __init__(self, config):
        self.config = config
        self.path = Path(config.RAG_INDEX_PATH)
        self._retry_after = 0
        self._query_cache = lru_cache(maxsize=128)(self._search_version)

    def fingerprint(self):
        versions = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size)
                         for p in sorted(Path(self.config.DATA_DIR).glob('*.chunks.json')))
        return self._fingerprint_versions(versions)

    @staticmethod
    @lru_cache(maxsize=16)
    def _fingerprint_versions(versions):
        digest = hashlib.sha256()
        for filename, modified, size in versions:
            path = Path(filename)
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    @staticmethod
    @lru_cache(maxsize=8)
    def _vectors(filename, modified, size):
        with sqlite3.connect(f'file:{filename}?mode=ro', uri=True) as db:
            vectors = []
            for id, raw in db.execute('select id,vector from vectors'):
                vector = json.loads(raw)
                norm = math.sqrt(sum(v*v for v in vector))
                if norm:
                    vectors.append((id, tuple(v/norm for v in vector)))
        return tuple(vectors)

    def status(self):
        if not self.path.exists():
            return dict(available=False, reason='Index not built; keyword retrieval is active.')
        try:
            with sqlite3.connect(f'file:{self.path}?mode=ro', uri=True) as db:
                info = dict(db.execute('select key,value from metadata'))
                count = db.execute('select count(*) from vectors').fetchone()[0]
            valid = info.get('fingerprint') == self.fingerprint() and info.get('model') == self.config.EMBEDDING_MODEL
            return dict(available=valid, chunks=count, model=info.get('model'),
                        reason=None if valid else 'Source data changed; rebuild the embedding index. Keyword retrieval is active.')
        except (sqlite3.Error, OSError):
            return dict(available=False, reason='Index unavailable; keyword retrieval is active.')

    def embed(self, texts):
        settings = self.config.ai_settings()
        if not settings or settings['provider'] != 'openai' or not settings['api_key']:
            raise RuntimeError('OpenAI credentials are required to build the semantic index.')
        try:
            response = requests.post(settings['base_url']+'/embeddings',
                                     headers={'Authorization': 'Bearer '+settings['api_key']},
                                     json={'model': self.config.EMBEDDING_MODEL, 'input': texts},
                                     timeout=min(self.config.AI_TIMEOUT_SECONDS, self.config.EMBEDDING_TIMEOUT_SECONDS))
        except requests.RequestException:
            raise RuntimeError('Cannot reach the embedding API. Check network connectivity.') from None
        if response.status_code >= 400:
            raise RuntimeError(f'Embedding API rejected the request (HTTP {response.status_code}). Check credentials, model access and quota.')
        try:
            data = sorted(response.json()['data'], key=lambda row: row['index'])
            vectors = [row['embedding'] for row in data]
            if len(vectors) != len(texts) or any(not v or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in v) for v in vectors):
                raise ValueError()
            return vectors
        except (KeyError, ValueError, TypeError):
            raise RuntimeError('Embedding API returned invalid vectors.') from None

    def build(self):
        chunks = []
        for path in sorted(Path(self.config.DATA_DIR).glob('*.chunks.json')):
            chunks.extend(c for c in json.loads(path.read_text()) if c['kind'] != 'record')
        if not chunks:
            raise RuntimeError('No preprocessed source chunks were found.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.building.sqlite')
        temporary.unlink(missing_ok=True)
        try:
            with sqlite3.connect(temporary) as db:
                db.execute('create table metadata(key text primary key,value text)')
                db.execute('create table vectors(id text primary key,vector text)')
                for start in range(0, len(chunks), 24):
                    batch = chunks[start:start+24]
                    # Retrieval still uses complete original chunks; this bounds embedding inputs.
                    vectors = self.embed([c['text'][:6000] for c in batch])
                    db.executemany('insert into vectors values(?,?)', [(c['id'], json.dumps(v)) for c,v in zip(batch,vectors)])
                db.executemany('insert into metadata values(?,?)', [('model',self.config.EMBEDDING_MODEL),('fingerprint',self.fingerprint())])
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return self.status()

    def search(self, question):
        if monotonic() < self._retry_after or not self.status()['available']:
            return {}
        try:
            stat = self.path.stat()
            return dict(self._query_cache(question, stat.st_mtime_ns, stat.st_size))
        except (RuntimeError, sqlite3.Error, ValueError, TypeError, OSError):
            self._retry_after = monotonic() + 30
            return {}  # Briefly avoid repeated failed provider calls; keep keyword RAG active.

    def _search_version(self, question, modified, size):
        query = self.embed([question[:6000]])[0]
        qnorm = math.sqrt(sum(v*v for v in query))
        if not qnorm:
            return {}
        query = tuple(v/qnorm for v in query)
        scores = {}
        for id, vector in self._vectors(str(self.path), modified, size):
            if len(vector) == len(query):
                score = sum(a*b for a,b in zip(vector, query))
                if score >= 0.32:
                    scores[id] = score
        return scores
