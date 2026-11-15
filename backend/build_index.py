"""Run after preprocessing to enable semantic + keyword RAG over saved source chunks."""
import json
from config import Config
from services.semantic_service import SemanticIndex

if __name__ == '__main__':
    try:
        print(json.dumps(SemanticIndex(Config()).build()))
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1)
