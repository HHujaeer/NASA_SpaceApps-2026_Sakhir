import pytest

from services.csv_service import (DataFileError, InvalidRequest, InvestigationNotFound, match_keywords)


def test_lists_files_and_skips_unreadable_ones(csv_service):
    assert set(csv_service.list_investigation_ids()) == {"flame_spread", "smoke_detection", "empty"}
    items, total, errors = csv_service.list_investigations()
    assert total == 2 and [i["id"] for i in items] == ["flame_spread", "smoke_detection"]
    assert errors and errors[0]["id"] == "empty"


def test_missing_data_directory_is_graceful(tmp_path):
    from config import Config
    from services.csv_service import CsvService
    svc = CsvService(Config(env={}, DATA_DIR=tmp_path / "nope"))
    assert svc.list_investigation_ids() == []
    assert svc.statistics()["investigation_count"] == 0


def test_profile_detects_fields_and_units(csv_service):
    p = csv_service.build_profile("flame_spread")
    assert p["detected_fields"]["oxygen"] == "O2_pct"
    assert p["name"] == "TestFlame"
    assert p["conditions"]["oxygen"]["min"] == 21 and p["conditions"]["oxygen"]["max"] == 30
    assert p["conditions"]["pressure"]["normalized"]["unit"] == "kPa"
    assert "Flame_Spread_mm_s" in p["measurements"]
    assert set(p["conditions"]["sensors"]["values"]) == {"thermocouple", "camera"}


def test_units_are_normalised_without_altering_raw_values(csv_service):
    p = csv_service.build_profile("smoke_detection")
    pressure = p["conditions"]["pressure"]
    assert pressure["unit"] == "psi" and pressure["min"] == 10.2  # raw value preserved
    assert pressure["normalized"]["min"] == pytest.approx(10.2 * 6.894757)


def test_missing_values_stay_missing(csv_service):
    data = csv_service.get_investigation("flame_spread", include_records=True)
    rec3 = data["records"][2]["values"]
    assert rec3["Flow_cm_s"] is None and rec3["Flame_Spread_mm_s"] is None  # not fabricated
    assert data["records"][0]["values"]["O2_pct"] == "21"                     # raw text preserved
    assert data["records"][2]["source"] == {"file": "flame_spread.csv", "row_number": 3, "source_reference": "SRC-A2"}
    assert data["data_quality"]["missing_cells"] > 0
    assert "_text" not in data


def test_unknown_or_malicious_id(csv_service):
    for bad in ("nope", "../flame_spread", "flame_spread.csv"):
        with pytest.raises(InvestigationNotFound):
            csv_service.get_investigation(bad)


def test_empty_file_raises_data_file_error(csv_service):
    with pytest.raises(DataFileError):
        csv_service.build_profile("empty")


def test_search_filter_sort(csv_service):
    items, total, _ = csv_service.list_investigations(q="smoke")
    assert [i["id"] for i in items] == ["smoke_detection"]
    items, _, _ = csv_service.list_investigations(fuel="beta")
    assert [i["id"] for i in items] == ["flame_spread"]
    items, _, _ = csv_service.list_investigations(sensor="camera")
    assert [i["id"] for i in items] == ["flame_spread"]
    # 26.5 % oxygen appears in the smoke file only (flame file spans 21-30, so both overlap)
    items, _, _ = csv_service.list_investigations(ranges={"oxygen": (29, None)})
    assert [i["id"] for i in items] == ["flame_spread"]
    items, _, _ = csv_service.list_investigations(sort="row_count", order="desc")
    assert items[0]["id"] == "flame_spread"
    with pytest.raises(InvalidRequest):
        csv_service.list_investigations(sort="bogus")


def test_statistics(csv_service):
    s = csv_service.statistics()
    assert s["investigation_count"] == 2 and s["total_records"] == 7
    assert s["condition_ranges_normalized"]["oxygen"]["max"] == 30
    assert s["unreadable_files"][0]["id"] == "empty"


def test_keyword_matching_rules():
    assert match_keywords("the iss cabin", ["iss"]) == ["iss"]
    assert match_keywords("mission control", ["iss"]) == []          # whole words only
    assert match_keywords("fire suppression system", ["suppress*"]) == ["suppress*"]
    assert match_keywords("space station crew", ["space station"]) == ["space station"]


# ----------------------------- upload / delete ------------------------------ #
import io  # noqa: E402

from services.csv_service import InvestigationExists  # noqa: E402


def _upload(client, name="new_study.csv", content=b"Experiment,O2_pct\nNewStudy,21\nNewStudy,30\n", **form):
    return client.post("/api/investigations", data={"file": (io.BytesIO(content), name), **form},
                       content_type="multipart/form-data")


def test_upload_creates_investigation_readable_immediately(client, data_dir):
    resp = _upload(client)
    body = resp.get_json()
    assert resp.status_code == 201 and body["success"] and body["meta"]["replaced"] is False
    assert body["data"]["id"] == "new_study" and body["data"]["row_count"] == 2
    assert (data_dir / "new_study.csv").exists() and not list(data_dir.glob(".*.upload"))
    assert client.get("/api/investigations/new_study").status_code == 200
    assert "new_study" in [i["id"] for i in client.get("/api/investigations").get_json()["data"]]


def test_upload_id_override_and_filename_sanitising(client, data_dir):
    assert _upload(client, id="my-id_1").get_json()["data"]["id"] == "my-id_1"
    assert _upload(client, name="Odd name (v2).csv").get_json()["data"]["id"] == "Odd_name_v2"


def test_upload_conflict_needs_overwrite(client, data_dir):
    first = (data_dir / "flame_spread.csv").read_text()
    resp = _upload(client, id="flame_spread")
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "investigation_exists"
    assert (data_dir / "flame_spread.csv").read_text() == first          # untouched
    ok_resp = _upload(client, id="flame_spread", overwrite="true")
    assert ok_resp.status_code == 200 and ok_resp.get_json()["meta"]["replaced"] is True
    assert (data_dir / "flame_spread.csv").read_text().startswith("Experiment,O2_pct")


def test_upload_validation(client, data_dir):
    before = sorted(p.name for p in data_dir.iterdir())
    assert client.post("/api/investigations", json={"x": 1}).status_code == 400            # no file
    assert _upload(client, name="notes.txt").status_code == 400                              # wrong type
    assert _upload(client, content=b"   \n").status_code == 400                              # empty
    assert _upload(client, id="../evil").status_code == 400                                  # unsafe id
    assert _upload(client, id="has space").status_code == 400
    assert _upload(client, content=b"OnlyHeader,O2\n").status_code == 422                   # no data rows
    assert sorted(p.name for p in data_dir.iterdir()) == before                              # nothing leaked in


def test_upload_size_limit(config, data_dir):
    from app import create_app
    config.MAX_UPLOAD_BYTES = 100
    c = create_app(config).test_client()
    assert _upload(c, content=b"a,b\n" + b"1,2\n" * 200).status_code in (400, 413)


def test_delete_investigation(client, data_dir):
    resp = client.delete("/api/investigations/smoke_detection")
    assert resp.status_code == 200 and resp.get_json()["data"]["deleted"] is True
    assert not (data_dir / "smoke_detection.csv").exists()
    assert client.get("/api/investigations/smoke_detection").status_code == 404
    assert client.delete("/api/investigations/smoke_detection").status_code == 404
    assert client.delete("/api/investigations/..%2Fapp").status_code == 404


def test_service_add_rejects_duplicates(csv_service):
    csv_service.add_investigation("dup", b"A,O2_pct\nx,21\n")
    with pytest.raises(InvestigationExists):
        csv_service.add_investigation("dup", b"A,O2_pct\nx,21\n")
