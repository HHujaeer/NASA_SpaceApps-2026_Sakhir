import pytest

from services.ai_service import AIServiceError
from services.csv_service import InvalidRequest, InvestigationNotFound


def test_compare_basic(comparison):
    res = comparison.compare(["flame_spread", "smoke_detection"])
    assert [i["tag"] for i in res["investigations"]] == ["E1", "E2"]
    oxygen = res["parameters"]["oxygen"]
    assert oxygen["status"] == "overlapping" and oxygen["overlap"] == [21.0, 26.5]
    assert res["parameters"]["pressure"]["basis"] == "normalised to kPa"   # psi vs kPa made comparable
    assert res["parameters"]["gravity"]["status"] in ("overlapping", "identical", "disjoint")


def test_missing_parameters_are_reported_not_invented(comparison):
    res = comparison.compare(["flame_spread", "smoke_detection"])
    assert res["parameters"]["flow"]["status"] == "insufficient_data"   # smoke file has no airflow column
    assert any("airflow is not reported in SmokeStudy" in n or "airflow is not reported in smoke_detection" in n
               for n in res["not_available"])
    assert "E2" not in res["parameters"]["flow"]["per_investigation"]


def test_discrete_differences_and_results(comparison):
    res = comparison.compare(["flame_spread", "smoke_detection"])
    assert res["parameters"]["sensors"]["status"] == "different"
    assert res["results"]["findings_not_reported_for"] == ["E1"]
    assert res["results"]["findings_text"]["E2"]


def test_validation(comparison):
    with pytest.raises(InvalidRequest):
        comparison.compare(["flame_spread"])
    with pytest.raises(InvalidRequest):
        comparison.compare(["flame_spread", "flame_spread"])
    with pytest.raises(InvalidRequest):
        comparison.compare("flame_spread,smoke_detection")
    with pytest.raises(InvestigationNotFound):
        comparison.compare(["flame_spread", "missing"])


def test_ai_explanation_uses_only_comparison_data(comparison, fake_ai):
    res = comparison.compare(["flame_spread", "smoke_detection"], explain=True)
    assert res["explanation"]["status"] == "ok"
    ctx = fake_ai.calls[0]["context"]
    assert "overlap" in ctx and "SmokeStudy" in ctx
    assert "Alpha-fabric" not in ctx or "material" in ctx  # only summarised profile values, no raw rows


def test_ai_failure_does_not_break_comparison(comparison, fake_ai):
    fake_ai.error = AIServiceError("ai_timeout", "slow", 504)
    res = comparison.compare(["flame_spread", "smoke_detection"], explain=True)
    assert res["explanation"] == {"status": "unavailable", "error": {"code": "ai_timeout", "message": "slow"}}
    assert res["parameters"]["oxygen"]["status"] == "overlapping"
