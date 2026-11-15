"""Test fixtures. All CSV data below is SYNTHETIC test data, not NASA data."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from config import Config  # noqa: E402
from services.ai_service import AIService  # noqa: E402
from services.comparison_service import ComparisonService  # noqa: E402
from services.csv_service import CsvService  # noqa: E402
from services.ranking_service import RankingService  # noqa: E402
from services.research_service import ResearchService  # noqa: E402

FLAME_CSV = """Experiment,Material,O2_pct,Pressure_kPa,Flow_cm_s,Gravity,Flame_Spread_mm_s,Sensor,Source,Notes
TestFlame,Alpha-fabric,21,101.3,5,microgravity,1.2,thermocouple,SRC-A1,baseline
TestFlame,Alpha-fabric,25,101.3,5,microgravity,2.4,thermocouple,SRC-A1,
TestFlame,Alpha-fabric,30,70.3,N/A,microgravity,,thermocouple;camera,SRC-A2,higher oxygen
TestFlame,Beta-sheet,25,70.3,10,microgravity,3.1,camera,SRC-A2,fire spread modeling data
"""

SMOKE_CSV = """Test_Name,Smoke Detector,Pressure (psi),Oxygen (%),Gravity_g,Obscuration_pct_m,Reference,Findings
SmokeStudy,photoelectric,14.7,21,0,0.5,REF-S1,detector alarm triggered
SmokeStudy,ionization,10.2,26.5,0,0.7,REF-S1,alarm triggered later
SmokeStudy,photoelectric,10.2,26.5,0.166,,REF-S2,smoke particle size reported
"""


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "experiments"
    d.mkdir()
    (d / "flame_spread.csv").write_text(FLAME_CSV)
    (d / "smoke_detection.csv").write_text(SMOKE_CSV)
    (d / "empty.csv").write_text("")  # unreadable file must not break listings
    return d


@pytest.fixture
def config(data_dir):
    return Config(env={}, DATA_DIR=data_dir)


@pytest.fixture
def csv_service(config):
    return CsvService(config)


@pytest.fixture
def ranking(config, csv_service):
    return RankingService(config, csv_service)


class FakeAI:
    """Stands in for AIService; records every prompt it receives."""

    def __init__(self, text=None, error=None):
        self.text = text or ("## Experimental results (from the data)\nValue reported [E1:R1].\n"
                             "## AI interpretation\nPossible trend [E1].\n## Data gaps\nNone noted.")
        self.error = error
        self.calls = []

    def generate(self, task, context, question=None):
        self.calls.append({"task": task, "context": context, "question": question})
        if self.error:
            raise self.error
        return {"text": self.text, "provider": "fake", "model": "fake-model", "usage": None}

    def is_configured(self):
        return True

    def status(self):
        return {"configured": True, "provider": "fake", "model": "fake-model", "missing": []}


@pytest.fixture
def fake_ai():
    return FakeAI()


@pytest.fixture
def research(config, csv_service, fake_ai):
    return ResearchService(config, csv_service, fake_ai)


@pytest.fixture
def comparison(config, csv_service, fake_ai):
    return ComparisonService(config, csv_service, fake_ai)


@pytest.fixture
def client(config):
    app = create_app(config)
    app.testing = True
    return app.test_client()
