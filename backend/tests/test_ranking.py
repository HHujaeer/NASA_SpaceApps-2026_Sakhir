import pytest

from services.csv_service import InvalidRequest


def test_ranking_structure_and_disclaimer(ranking):
    res = ranking.rank("fire_detection")
    assert "not NASA-approved" in res["disclaimer"]
    assert [r["rank"] for r in res["ranked"]] == [1, 2]
    top = res["ranked"][0]
    assert set(top["criteria"]) == {"mission_relevance", "fire_safety_relevance", "data_quality",
                                    "environmental_similarity", "predictive_modeling_value"}
    assert top["criteria"]["data_quality"]["explanation"]
    assert top["supporting_data"]["file"].endswith(".csv")
    assert res["unreadable_files"][0]["id"] == "empty"


def test_category_changes_criterion_scores(ranking):
    def crit(category, inv_id, name):
        row = next(r for r in ranking.rank(category)["ranked"] if r["id"] == inv_id)
        return row["criteria"][name]["score"]

    # The smoke file is the stronger fire-safety match for detection than the flame file ...
    assert crit("fire_detection", "smoke_detection", "fire_safety_relevance") > \
        crit("fire_detection", "flame_spread", "fire_safety_relevance")
    # ... and the same file scores differently for a different category's keywords.
    assert crit("fire_detection", "smoke_detection", "fire_safety_relevance") > \
        crit("fire_suppression", "smoke_detection", "fire_safety_relevance")
    # Mission relevance depends on keywords present in the file (flame file mentions microgravity).
    assert crit("iss_spacecraft", "flame_spread", "mission_relevance") > \
        crit("iss_spacecraft", "smoke_detection", "mission_relevance")


def test_default_weights_match_specification(ranking):
    assert ranking.rank("iss_spacecraft")["weights_percent"] == {
        "mission_relevance": 30.0, "fire_safety_relevance": 25.0, "data_quality": 20.0,
        "environmental_similarity": 15.0, "predictive_modeling_value": 10.0}


def test_score_is_weighted_sum_of_criteria(ranking):
    top = ranking.rank("lunar_habitat")["ranked"][0]
    assert top["score"] == pytest.approx(sum(c["weighted_points"] for c in top["criteria"].values()), abs=0.2)
    assert 0 <= top["score"] <= 100


def test_custom_weights_are_normalised(ranking):
    res = ranking.rank("fire_detection", weights={"data_quality": 100, "mission_relevance": 0, "fire_safety_relevance": 0,
                                                  "environmental_similarity": 0, "predictive_modeling_value": 0})
    assert res["weights_percent"]["data_quality"] == 100.0
    top = res["ranked"][0]
    assert top["score"] == top["criteria"]["data_quality"]["score"]


def test_environmental_similarity_uses_normalised_units(ranking):
    # smoke file: 10.2 psi = 70.3 kPa and 26.5 % O2 -> matches the lunar reference closely
    smoke = next(r for r in ranking.rank("lunar_habitat")["ranked"] if r["id"] == "smoke_detection")
    assert smoke["criteria"]["environmental_similarity"]["score"] > 50


def test_invalid_input(ranking):
    with pytest.raises(InvalidRequest):
        ranking.rank("not_a_category")
    with pytest.raises(InvalidRequest):
        ranking.rank("fire_detection", weights={"bogus": 1})
    with pytest.raises(InvalidRequest):
        ranking.rank("fire_detection", weights={"data_quality": -5})
    with pytest.raises(InvalidRequest):
        ranking.resolve_weights({k: 0 for k in ("mission_relevance", "fire_safety_relevance", "data_quality",
                                                "environmental_similarity", "predictive_modeling_value")})
