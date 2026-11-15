"""Deployment wiring (D-027): readiness, SPA serving, CORS, public-demo notes, case limits, data fetch/verify.
All offline; GSOD rows are synthetic (never real station data)."""

import json

import pytest
from fastapi.testclient import TestClient

from earthsignal import cases as cases_mod
from earthsignal.api.main import create_app
from earthsignal.config import DeploySettings
from earthsignal.data import deploy_data, gsod, power

from .test_api import synthetic_client  # noqa: F401  (fixture re-use)
from .test_gsod import row, year_csv


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>EarthSignal</title><div id=root></div>")
    (d / "assets" / "index-abc123.js").write_text("console.log(1)")
    (d / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside dist")
    return d


def test_ready_is_503_without_power_data(tmp_path):
    c = TestClient(create_app(processed_root=tmp_path / "none"))
    r = c.get("/api/ready")
    assert r.status_code == 503
    assert r.json()["ready"] is False
    assert c.get("/api/health").status_code == 200  # liveness stays up so the logs can explain


def test_ready_reports_missing_optional_sources(synthetic_client):  # noqa: F811
    r = synthetic_client.get("/api/ready").json()
    # The synthetic fixture only has the eastern cell, so the server is not ready and says which part is missing.
    assert r["required"]["nasa_power"]["lucknow"] is not None
    assert r["required"]["nasa_power"]["lucknow_airport"] is None
    assert r["optional"]["noaa_gsod_station"] is None


def test_frontend_served_with_spa_fallback(tmp_path, dist):
    c = TestClient(create_app(processed_root=tmp_path / "none", settings=DeploySettings(frontend_dist=dist)))
    assert "EarthSignal" in c.get("/").text
    assert "EarthSignal" in c.get("/response/anything").text  # refresh on a client-side URL
    assert c.get("/response/anything").headers["cache-control"] == "no-cache"
    a = c.get("/assets/index-abc123.js")
    assert a.text == "console.log(1)" and "immutable" in a.headers["cache-control"]
    assert c.get("/favicon.svg").text == "<svg/>"
    r = c.get("/api/does-not-exist")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/api").json()["service"] == "EarthSignal API"
    assert "outside dist" not in c.get("/..%2Fsecret.txt").text
    assert "outside dist" not in c.get("/assets/..%2F..%2Fsecret.txt").text


def test_missing_frontend_build_fails_loudly(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        create_app(processed_root=tmp_path / "none", settings=DeploySettings(frontend_dist=tmp_path / "nowhere"))


def test_cors_only_when_configured(tmp_path):
    origin = "https://ui.example.org"
    plain = TestClient(create_app(processed_root=tmp_path / "none"))
    assert "access-control-allow-origin" not in plain.get("/api/health", headers={"Origin": origin}).headers
    split = TestClient(create_app(processed_root=tmp_path / "none", settings=DeploySettings(cors_origins=(origin,))))
    assert split.get("/api/health", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin
    assert "access-control-allow-origin" not in split.get("/api/health", headers={"Origin": "https://evil.example"}).headers


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EARTHSIGNAL_FRONTEND_DIST", str(tmp_path))
    monkeypatch.setenv("EARTHSIGNAL_CORS_ORIGINS", "https://a.example/, https://b.example")
    monkeypatch.setenv("EARTHSIGNAL_WARMUP", "1")
    monkeypatch.delenv("EARTHSIGNAL_PUBLIC_DEMO", raising=False)
    s = DeploySettings.from_env()
    assert s.frontend_dist == tmp_path and s.cors_origins == ("https://a.example", "https://b.example")
    assert s.warmup is True and s.public_demo is False


def test_public_demo_note(tmp_path):
    off = TestClient(create_app(processed_root=tmp_path / "none", cases_path=tmp_path / "c.json"))
    on = TestClient(create_app(processed_root=tmp_path / "none", cases_path=tmp_path / "c.json",
                               settings=DeploySettings(public_demo=True)))
    assert off.get("/api/cases").json()["storage_note"] is None
    assert "visible to every visitor" in on.get("/api/cases").json()["storage_note"]
    assert on.get("/api/health").json()["public_demo"] is True


def test_audit_trail_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(cases_mod, "MAX_AUDIT_ENTRIES", 3)
    store = cases_mod.CaseStore(tmp_path / "cases.json")
    c = store.create({"id": "E1", "kind": "heat", "start": "2002-07-19"}, {})
    store.add_note(c["id"], "first")
    store.add_note(c["id"], "second")
    with pytest.raises(cases_mod.CaseError, match="maximum"):
        store.add_note(c["id"], "third")
    with pytest.raises(cases_mod.CaseError, match="maximum"):
        store.transition(c["id"], "investigating", "")


def test_compare_checksums():
    r = deploy_data.compare({"2000": "a", "2001": "b", "2002": "c"}, {"2000": "a", "2001": "x", "2003": "d"})
    assert r == {"matched": ["2000"], "changed": ["2001"], "missing": ["2002"], "extra": ["2003"]}


def _gsod_manifest(payload: bytes) -> dict:
    return {"station": "42369099999", "years": [2023, 2023], "sha256": {"2023": power.sha256_bytes(payload)}}


def test_fetch_gsod_verifies_and_processes(tmp_path):
    payload = year_csv([row("2023-01-01", 50.0, 24, "0.00", "G")])
    ok = deploy_data.fetch_gsod(_gsod_manifest(payload), tmp_path / "raw", tmp_path / "processed", strict=True,
                                http_get_status=lambda url: (200, payload))
    assert ok and gsod.latest(tmp_path / "processed") is not None
    # Second run sees processed data and does not download again.
    assert deploy_data.fetch_gsod(_gsod_manifest(payload), tmp_path / "raw", tmp_path / "processed", strict=True,
                                  http_get_status=lambda url: pytest.fail("should not download"))


def test_fetch_gsod_strict_rejects_changed_file(tmp_path, capsys):
    analysed = year_csv([row("2023-01-01", 50.0, 24, "0.00", "G")])
    served = year_csv([row("2023-01-01", 51.0, 24, "0.00", "G")])
    ok = deploy_data.fetch_gsod(_gsod_manifest(analysed), tmp_path / "raw", tmp_path / "processed", strict=True,
                                http_get_status=lambda url: (200, served))
    assert not ok and gsod.latest(tmp_path / "processed") is None
    assert "changed: 2023" in capsys.readouterr().out
    # Without --strict the new file is accepted; its own checksum is recorded in the provenance.
    assert deploy_data.fetch_gsod(_gsod_manifest(analysed), tmp_path / "raw2", tmp_path / "processed", strict=False,
                                  http_get_status=lambda url: (200, served))
    prov = gsod.latest(tmp_path / "processed")[1]
    assert prov["files"][0]["sha256"] == power.sha256_bytes(served)


def test_committed_manifests_hold_checksums_only():
    for name in (deploy_data.GSOD_MANIFEST, deploy_data.IMD_MANIFEST):
        m = deploy_data.load_manifest(name)
        assert m["sha256"] and all(len(v) == 64 for v in m["sha256"].values())
        assert set(m) <= {"source", "station", "years", "url_template", "download_url", "recorded_from_dataset", "note", "sha256"}
        assert len(json.dumps(m)) < 10_000


def test_warmup_runs_in_background_and_never_crashes(tmp_path):
    import time

    app = create_app(processed_root=tmp_path / "none", settings=DeploySettings(warmup=True))
    with TestClient(app) as c:  # the context manager runs the startup (lifespan) hook
        for _ in range(100):
            state = c.get("/api/ready").json()["forecast_warmup"]
            if state["done"]:
                break
            time.sleep(0.05)
        assert state == {"enabled": True, "done": True, "error": None}  # no data: skipped quietly, server still up



def test_forecast_evaluation_cached_at_build_and_reused(tmp_path, sample_doc, metadata_bytes, monkeypatch):
    """SYNTHETIC POWER data. The build step caches the evaluation; a fresh server then answers without recomputing."""
    from datetime import date

    from earthsignal.api import forecast as fapi
    from earthsignal.config import LUCKNOW
    from earthsignal.data import ingest

    from .conftest import synthetic_power_doc

    doc = json.dumps(synthetic_power_doc(sample_doc, "1981-01-01", "2026-01-31")).encode()
    raw = ingest.download(LUCKNOW, date(1981, 1, 1), date(2026, 1, 31), raw_root=tmp_path / "raw",
                          http_get=lambda url: metadata_bytes if "/system/manager/parameters" in url else doc)
    ingest.process(raw, processed_root=tmp_path / "processed")
    cache = tmp_path / "cache"
    assert deploy_data.precompute_forecast(cache, tmp_path / "processed") is False  # western cell has no data here
    files = list(cache.glob("forecast_evaluation_lucknow_*.json"))
    assert len(files) == 1 and fapi.CODE_TAG in files[0].name

    monkeypatch.setattr(fapi.fc, "evaluate", lambda folds: pytest.fail("cached evaluation should be reused"))
    monkeypatch.setattr(fapi.fc, "run_folds", lambda *a, **k: pytest.fail("cached evaluation should be reused"))
    c = TestClient(create_app(processed_root=tmp_path / "processed", settings=DeploySettings(cache_dir=cache)))
    r = c.get("/api/forecast?area=lucknow")
    assert r.status_code == 200 and r.json()["evaluation"] == json.loads(files[0].read_text())
