import pytest

from services.ai_service import AIServiceError
from services.csv_service import InvalidRequest


# ----------------------------- research service ----------------------------- #
def test_ask_retrieves_only_relevant_data(research, fake_ai):
    res = research.ask("How does smoke detector alarm timing differ between detector types?")
    assert res["answerable"] and res["ai"]["model"] == "fake-model"
    ctx = fake_ai.calls[0]["context"]
    assert "[E1] Experiment: SmokeStudy" in ctx and "ionization" in ctx
    assert "Alpha-fabric" not in ctx                      # unrelated file was not sent
    assert {r["investigation_id"] for r in res["references"]} == {"smoke_detection"}
    assert any(r["type"] == "record" and r["source_reference"] for r in res["references"])


def test_ask_matches_numbers_in_records(research, fake_ai):
    research.ask("What flame spread was seen at 30 percent oxygen?")
    ctx = fake_ai.calls[0]["context"]
    assert "[E1:R3]" in ctx                                 # the row with O2_pct = 30


def test_ask_without_matching_data_does_not_call_ai(research, fake_ai):
    res = research.ask("Tell me about tribology of gearbox lubricants")
    assert res["answerable"] is False and res["answer"] is None
    assert "No records" in res["message"] and fake_ai.calls == []


def test_ask_validation(research):
    for bad in ("", "  ", None, "x" * 2000, "the and for"):
        with pytest.raises(InvalidRequest):
            research.ask(bad)


def test_ai_failure_keeps_references(research, fake_ai):
    fake_ai.error = AIServiceError("ai_unreachable", "down", 502)
    with pytest.raises(AIServiceError) as exc:
        research.ask("smoke detector alarm")
    assert exc.value.details["references"] and exc.value.details["retrieval"]


def test_sections_and_citation_check(research):
    res = research.ask("smoke detector alarm")
    assert set(res["sections"]) == {"experimental_results", "ai_interpretation", "data_gaps"}
    assert res["citation_check"]["all_citations_valid"]
    check = research.check_citations("see [E9:R1] and [E1]", {"E1"})
    assert check["unknown_citations"] == ["E9:R1"] and not check["all_citations_valid"]


def test_summarize_includes_facts_and_references(research, fake_ai):
    res = research.summarize("flame_spread")
    assert res["facts"]["row_count"] == 4 and res["name"] == "TestFlame"
    assert "Aggregate over all rows, Flame_Spread_mm_s" in fake_ai.calls[0]["context"]
    assert "_text" not in res["facts"]


def test_insights(research, fake_ai):
    res = research.insights("smoke_detection")
    assert res["topic_label"] == "Smoke detection"
    assert "'## Measured findings'" in fake_ai.calls[0]["task"]
    with pytest.raises(InvalidRequest):
        research.insights("astrology")
    with pytest.raises(InvalidRequest):
        research.insights("smoke_detection", investigation_ids=["nope"])


def test_context_is_size_limited(config, csv_service, fake_ai):
    from services.research_service import ResearchService
    config.MAX_CONTEXT_CHARS = 400
    res = ResearchService(config, csv_service, fake_ai).ask("smoke detector alarm")
    assert res["context_truncated"] and len(fake_ai.calls[0]["context"]) <= 700


# ---------------------------------- API ------------------------------------ #
def test_api_envelope_and_data_endpoints(client):
    r = client.get("/api/health").get_json()
    assert r["success"] and r["data"]["csv_files_found"] == 3 and r["data"]["ai"]["configured"] is False
    lst = client.get("/api/investigations?q=smoke").get_json()
    assert lst["success"] and lst["meta"]["total"] == 1 and lst["data"][0]["id"] == "smoke_detection"
    one = client.get("/api/investigations/flame_spread?include_records=true&limit=2").get_json()
    assert len(one["data"]["records"]) == 2 and one["data"]["records_total"] == 4
    assert client.get("/api/statistics").get_json()["data"]["investigation_count"] == 2


def test_api_errors_are_json(client):
    r = client.get("/api/investigations/missing")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "investigation_not_found"
    assert client.get("/api/investigations?min_oxygen=abc").status_code == 400
    assert client.get("/api/investigations?limit=-1").status_code == 400
    assert client.post("/api/ask", data="not json").status_code == 400
    assert client.get("/api/nothing").get_json()["error"]["code"] == "not_found"
    assert client.get("/api/ask").status_code == 405
    assert client.get("/api/investigations/empty").status_code == 422


def test_api_ranking_and_compare(client):
    r = client.get("/api/rankings?category=fire_detection").get_json()
    assert {x["id"] for x in r["data"]["ranked"]} == {"flame_spread", "smoke_detection"}
    assert [x["rank"] for x in r["data"]["ranked"]] == [1, 2]
    assert client.get("/api/rankings").status_code == 400
    r = client.post("/api/rankings", json={"category": "lunar_habitat", "weights": {"data_quality": 50}, "limit": 1})
    assert len(r.get_json()["data"]["ranked"]) == 1
    assert client.post("/api/rankings", json={"category": "bogus"}).status_code == 400
    r = client.post("/api/compare", json={"ids": ["flame_spread", "smoke_detection"]})
    assert r.get_json()["data"]["parameters"]["oxygen"]["status"] == "overlapping"
    assert client.post("/api/compare", json={"ids": ["flame_spread"]}).status_code == 400


def test_api_ai_endpoints_report_unconfigured_ai_with_references(client):
    r = client.post("/api/ask", json={"question": "smoke detector alarm"})
    body = r.get_json()
    assert r.status_code == 503 and body["error"]["code"] == "ai_not_configured"
    assert body["error"]["details"]["references"]          # retrieved evidence is still returned
    assert client.post("/api/ask", json={"question": "gearbox lubricants"}).get_json()["data"]["answerable"] is False
    assert client.post("/api/summarize", json={"investigation_id": "smoke_detection"}).status_code == 503
    assert client.post("/api/summarize", json={"investigation_id": "zzz"}).status_code == 404
    assert client.post("/api/insights", json={"topic": "smoke_detection"}).status_code == 503
    assert len(client.get("/api/insights/topics").get_json()["data"]) == 6


def test_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["Access-Control-Allow-Origin"] in ("*", "http://localhost:3000")
