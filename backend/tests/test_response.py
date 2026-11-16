"""Response Intelligence tests: detection, investigation, cases and API. All series are SYNTHETIC."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from earthsignal import cases as cases_mod
from earthsignal.analysis import events as ev
from earthsignal.api.main import create_app
from earthsignal.api.response import PUBLIC_DEMO_NOTE
from earthsignal.cases import STATUS_HELP, TRANSITIONS, CaseError, CaseStore, brief_markdown
from earthsignal.config import LUCKNOW, LUCKNOW_AIRPORT, DeploySettings
from earthsignal.data import ingest

from .conftest import synthetic_power_doc


def climate(start="1991-01-01", end="2022-12-31", seed=0):
    idx = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    t = 25 + 8 * np.sin(2 * np.pi * (idx.dayofyear - 100) / 365.25) + rng.normal(0, 1.0, idx.size)
    p = np.where(rng.random(idx.size) < 0.3, rng.gamma(1.0, 8.0, idx.size), 0.0)
    return pd.Series(t, index=idx), pd.Series(p, index=idx)


# ---------------- calendar and thresholds
def test_doy365_maps_leap_days():
    idx = pd.DatetimeIndex(["2020-02-28", "2020-02-29", "2020-03-01", "2021-03-01", "2020-12-31"])
    assert ev.doy365(idx).tolist() == [59, 59, 60, 60, 365]


def test_doy_percentile_follows_season_and_window():
    t, _ = climate()
    thr = ev.doy_percentile(t, 95.0)
    assert np.isnan(thr[0]) and not np.isnan(thr[1:]).any()
    assert thr[196] > thr[15]  # July hotter than mid-January
    with pytest.raises(ValueError):
        ev.doy_percentile(t, 95.0, baseline=(1900, 1901))


def test_wet_percentile_uses_wet_days_only():
    idx = pd.date_range("1991-01-01", periods=1000, freq="D")
    p = pd.Series(np.where(np.arange(1000) % 2 == 0, 0.0, np.arange(1000) % 100), index=idx, dtype=float)
    wet = p[p >= 1]
    assert ev.wet_percentile(p, 99.0) == pytest.approx(np.percentile(wet, 99.0))
    with pytest.raises(ValueError):
        ev.wet_percentile(pd.Series([0.0] * 100, index=idx[:100]), 99.0)


# ---------------- detection
def test_detect_heat_finds_injected_episode_and_respects_min_days():
    t, _ = climate()
    t.loc["2021-07-10":"2021-07-14"] += 8  # 5-day episode
    t.loc["2021-09-01":"2021-09-02"] += 8  # only 2 days: below the 3-day minimum
    found, _ = ev.detect_heat(t, "lucknow")
    starts = {e.start: e for e in found}
    hit = [e for e in found if e.start <= "2021-07-10" <= e.end or e.start.startswith("2021-07-1")]
    assert hit and hit[0].days >= 5 and hit[0].rank == 1  # the injected episode is the most severe
    assert not any(e.start.startswith("2021-09-0") for e in found)
    assert all(e.days >= 3 for e in found) and "heat-lucknow-" in next(iter(starts.values())).id


def test_missing_day_breaks_an_episode():
    t, _ = climate()
    t.loc["2021-07-10":"2021-07-16"] += 8
    t.loc["2021-07-13"] = np.nan
    found, _ = ev.detect_heat(t, "lucknow")
    july = [e for e in found if e.start.startswith("2021-07-1")]
    assert all(e.end < "2021-07-13" or e.start > "2021-07-13" for e in july)  # never spans the gap


def test_detect_rain_merges_consecutive_days_and_ranks():
    _, p = climate()
    p.loc["2021-08-01":"2021-08-02"] = 500.0
    p.loc["2022-08-01"] = 300.0
    found, thr = ev.detect_rain(p, "lucknow")
    top = sorted(found, key=lambda e: e.rank)
    assert top[0].start == "2021-08-01" and top[0].days == 2 and top[0].severity == pytest.approx(1000.0)
    assert top[1].severity == pytest.approx(300.0)
    assert top[0].years_with_event_this_severe == 1 and top[0].severity_band == "top 10% of detected events"
    assert all(e.peak_value >= thr for e in found)


def test_provisional_flag():
    _, p = climate()
    p.loc["2022-12-30"] = 500.0
    found, _ = ev.detect_rain(p, "lucknow", provisional_from=pd.Timestamp("2022-12-01"))
    last = max(found, key=lambda e: e.start)
    assert last.provisional and not min(found, key=lambda e: e.start).provisional


def test_per_year_counts():
    e1 = ev.Event("a", "rain", "x", "2001-01-01", "2001-01-01", 1, 1, "2001-01-01", 1, 1, "mm", False)
    e2 = ev.Event("b", "rain", "x", "2001-06-01", "2001-06-01", 1, 1, "2001-06-01", 1, 1, "mm", False)
    assert ev.per_year_counts([e1, e2], [2000, 2001]) == {"years": [2000, 2001], "counts": [0, 2]}


# ---------------- investigation
def test_station_check_uses_own_threshold_and_min_obs():
    idx = pd.date_range("2005-01-01", "2024-12-31", freq="D")
    st = pd.DataFrame({"tmean_c": 25.0 + np.random.default_rng(1).normal(0, 1, idx.size), "temp_obs": 24}, index=idx)
    st.loc["2020-05-01":"2020-05-05", "tmean_c"] += 10
    c = ev.station_heat_check(st, "2020-05-01", "2020-05-05")
    assert c["verdict"] == "corroborated" and c["days_above"] == 5
    st.loc["2020-05-01":"2020-05-05", "temp_obs"] = 6  # sparse-observation days are not used
    assert ev.station_heat_check(st, "2020-05-01", "2020-05-05")["verdict"] == "no_data"
    assert ev.station_heat_check(None, "2020-05-01", "2020-05-05")["verdict"] == "no_data"


def test_source_rain_check_window_and_availability():
    _, p = climate("1998-01-01", "2024-12-31")
    p.loc["2010-08-06"] = 400.0  # one day AFTER the event: inside the +-1 day window
    c = ev.source_rain_check(p, "IMD", "2010-08-04", "2010-08-05", (1998, 2024))
    assert c["verdict"] == "corroborated" and c["window"] == ["2010-08-03", "2010-08-06"]
    assert ev.source_rain_check(p, "IMERG", "2026-01-01", "2026-01-02", (2001, 2020), available_until="2025-09-30")["verdict"] == "no_data"
    assert ev.source_rain_check(None, "IMD", "2010-08-04", "2010-08-05", (1998, 2024))["verdict"] == "no_data"


def test_plain_summary_counts_only_independent_sources():
    e = ev.Event("rain-lucknow-2000-08-29", "rain", "lucknow", "2000-08-29", "2000-08-30", 2, 150.0, "2000-08-29", 58.0, 282.0, "mm",
                 False, rank=1, n_events=47, years_with_event_this_severe=1, n_years=46)
    checks = [{"independent": False, "verdict": "corroborated"},
              {"independent": True, "verdict": "not_corroborated"}, {"independent": True, "verdict": "not_corroborated"}]
    s = ev.plain_summary(e, checks, True)
    assert "None of the 2 available independent" in s and "artifact" in s
    checks[1]["verdict"] = "corroborated"
    assert "1 of 2 available independent sources" in ev.plain_summary(e, checks, False)
    assert "cannot be cross-checked" in ev.plain_summary(e, [{"independent": True, "verdict": "no_data"}], None)


# ---------------- cases
EVENT = {"id": "heat-lucknow-2002-07-19", "kind": "heat", "area": "lucknow", "start": "2002-07-19", "end": "2002-07-30", "days": 12,
         "peak_value": 38.3, "peak_date": "2002-07-25", "severity": 27.6, "severity_unit": "°C-days", "rank": 1, "n_events": 77, "provisional": False}


def test_case_lifecycle_and_audit(tmp_path):
    store = CaseStore(tmp_path / "cases.json")
    c = store.create(EVENT, {"summary": "s", "checks": [], "method": ["m"], "data": ["d"]})
    assert c["id"] == "CASE-0001" and c["status"] == "open"
    assert store.create(EVENT, {})["id"] == "CASE-0001"  # one case per event
    with pytest.raises(CaseError):
        store.transition(c["id"], "confirmed", "reason given")  # must investigate first
    store.transition(c["id"], "investigating", "")
    with pytest.raises(CaseError, match="reason"):
        store.transition(c["id"], "confirmed", "")
    store.transition(c["id"], "confirmed", "Station corroborates.")
    with pytest.raises(CaseError, match="reason"):
        store.transition(c["id"], "investigating", "")  # reopening needs a reason too
    store.add_note(c["id"], "Checked IMD tables.")
    final = store.get(c["id"])
    assert [a["action"] for a in final["audit"]] == ["created", "status", "status", "note"]
    assert json.loads((tmp_path / "cases.json").read_text(encoding="utf-8"))[0]["status"] == "confirmed"
    md = brief_markdown(final)
    assert "NOT a forecast" in md and "Station corroborates." in md and "Checked IMD tables." in md
    with pytest.raises(KeyError):
        store.transition("CASE-9999", "investigating", "")
    with pytest.raises(CaseError):
        store.transition(c["id"], "teleported", "xxxxx")


# ---------------- API
@pytest.fixture
def client(tmp_path, sample_doc, metadata_bytes):
    for area in (LUCKNOW, LUCKNOW_AIRPORT):
        doc = synthetic_power_doc(sample_doc, "1990-01-01", "2022-12-31", seed=5)
        doc["properties"]["parameter"]["PRECTOTCORR"]["20150801"] = 400.0
        payload = json.dumps(doc).encode()
        get = lambda url, pl=payload: metadata_bytes if "/system/manager/parameters" in url else pl
        raw = ingest.download(area, date(1990, 1, 1), date(2022, 12, 31), raw_root=tmp_path / "raw", http_get=get)
        ingest.process(raw, processed_root=tmp_path / "processed")
    return TestClient(create_app(processed_root=tmp_path / "processed", cases_path=tmp_path / "cases" / "cases.json"))


def test_api_detect_investigate_respond(client):
    b = client.get("/api/response/events", params={"kind": "rain"}).json()
    assert b["data_kind"] == "derived_statistic" and "Not forecasts" in b["note"]
    top = min(b["events"], key=lambda e: e["rank"])
    assert top["start"] == "2015-08-01"
    inv = client.get("/api/response/investigate", params={"kind": "rain", "event_id": top["id"]}).json()
    assert inv["summary"] and inv["window"]["units"] == "mm/day" and len(inv["window"]["dates"]) == len(inv["window"]["threshold"])
    assert any(c["independent"] is False for c in inv["checks"])  # the other cell is labelled not independent
    assert all(c["verdict"] == "no_data" for c in inv["checks"] if c["independent"])  # no IMERG/IMD in this temp dir
    case = client.post("/api/cases", json={"area": "lucknow", "kind": "rain", "event_id": top["id"]}).json()
    assert case["evidence_snapshot"]["summary"] == inv["summary"]  # evidence recomputed server-side
    cid = case["id"]
    assert client.post(f"/api/cases/{cid}/status", json={"to": "dismissed", "note": "no reason"}).status_code == 422
    assert client.post(f"/api/cases/{cid}/status", json={"to": "investigating"}).json()["status"] == "investigating"
    assert client.post(f"/api/cases/{cid}/status", json={"to": "needs_data", "note": ""}).status_code == 422
    assert client.post(f"/api/cases/{cid}/status", json={"to": "needs_data", "note": "Waiting for IMD 2015."}).json()["status"] == "needs_data"
    assert client.post(f"/api/cases/{cid}/notes", json={"text": "Asked the team."}).status_code == 200
    lst = client.get("/api/cases").json()
    assert lst["cases"][0]["id"] == cid and "escalated" in lst["statuses"]
    brief = client.get(f"/api/cases/{cid}/brief")
    assert brief.status_code == 200 and "attachment" in brief.headers["content-disposition"] and "Asked the team." in brief.text


def test_api_rejects_bad_requests(client):
    assert client.get("/api/response/events", params={"area": "mars"}).status_code == 422
    assert client.get("/api/response/events", params={"kind": "wind"}).status_code == 422
    assert client.get("/api/response/investigate", params={"kind": "heat", "event_id": "heat-lucknow-1800-01-01"}).status_code == 404
    assert client.post("/api/cases", json={"area": "lucknow", "kind": "heat", "event_id": "nope"}).status_code == 404
    assert client.post("/api/cases/CASE-9999/status", json={"to": "investigating"}).status_code == 404
    assert client.get("/api/cases/CASE-9999/brief").status_code == 404


def seed_cases(tmp_path, monkeypatch, stamps, count=None):
    ticks = iter(stamps)
    monkeypatch.setattr(cases_mod, "_now", lambda: next(ticks))
    store = CaseStore(tmp_path / "cases.json")
    ids = [store.create(dict(EVENT, id=f"heat-lucknow-2000-{i:04d}"), {"summary": f"s{i}"})["id"] for i in range(count or len(stamps))]
    return store, ids


def minute_stamps(n):
    return [f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00+00:00" for i in range(n)]


def list_client(tmp_path, public_demo=False):
    return TestClient(create_app(processed_root=tmp_path / "none", cases_path=tmp_path / "cases.json",
                                 settings=DeploySettings(public_demo=public_demo)))


def page(client, **params):
    res = client.get("/api/cases", params=params)
    assert res.status_code == 200
    body = res.json()
    return [c["id"] for c in body["cases"]], body["pagination"]


def test_case_list_pages_through_every_case_exactly_once(tmp_path, monkeypatch):
    store, ids = seed_cases(tmp_path, monkeypatch, minute_stamps(57))
    newest_first = ids[::-1]
    assert [c["id"] for c in store.list()] == newest_first
    client = list_client(tmp_path)
    first, meta = page(client)
    assert first == newest_first[:25] and meta == {"total": 57, "limit": 25, "offset": 0, "has_more": True}
    seen = []
    for offset, size, more in [(0, 25, True), (25, 25, True), (50, 7, False)]:
        got, meta = page(client, limit=25, offset=offset)
        assert len(got) == size and meta == {"total": 57, "limit": 25, "offset": offset, "has_more": more}
        seen += got
    assert seen == newest_first and len(set(seen)) == 57
    assert page(client, limit=10, offset=20) == (newest_first[20:30], {"total": 57, "limit": 10, "offset": 20, "has_more": True})
    assert page(client, limit=19, offset=38) == (newest_first[38:], {"total": 57, "limit": 19, "offset": 38, "has_more": False})
    assert page(client, limit=1) == (newest_first[:1], {"total": 57, "limit": 1, "offset": 0, "has_more": True})
    assert page(client, limit=100) == (newest_first, {"total": 57, "limit": 100, "offset": 0, "has_more": False})
    for offset in (57, 1000):
        assert page(client, offset=offset) == ([], {"total": 57, "limit": 25, "offset": offset, "has_more": False})


def test_case_list_caps_a_page_at_100(tmp_path, monkeypatch):
    _, ids = seed_cases(tmp_path, monkeypatch, minute_stamps(101))
    client = list_client(tmp_path)
    got, meta = page(client, limit=100)
    assert got == ids[::-1][:100] and meta == {"total": 101, "limit": 100, "offset": 0, "has_more": True}
    assert page(client, limit=100, offset=100) == ([ids[0]], {"total": 101, "limit": 100, "offset": 100, "has_more": False})
    assert client.get("/api/cases", params={"limit": 101}).status_code == 422


def test_case_list_of_an_empty_store(tmp_path):
    client = list_client(tmp_path)
    for offset in (0, 50):
        assert page(client, offset=offset) == ([], {"total": 0, "limit": 25, "offset": offset, "has_more": False})
    assert not (tmp_path / "cases.json").exists()


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"limit": -1}, {"offset": -1}, {"limit": "ten"},
                                    {"limit": "2.5"}, {"offset": "1.5"}, {"offset": "first"}])
def test_case_list_rejects_invalid_pagination(tmp_path, params):
    res = list_client(tmp_path).get("/api/cases", params=params)
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert isinstance(detail, list) and [d["loc"] for d in detail] == [["query", next(iter(params))]]


def test_case_list_keeps_the_existing_order_for_tied_timestamps(tmp_path, monkeypatch):
    stamps = ["2026-01-01T00:00:00+00:00"] * 4 + ["2026-01-01T00:00:05+00:00"]
    store, ids = seed_cases(tmp_path, monkeypatch, stamps)
    expected = [ids[4], ids[0], ids[1], ids[2], ids[3]]
    assert [c["id"] for c in store.list()] == expected
    client = list_client(tmp_path)
    assert page(client, limit=2)[0] + page(client, limit=2, offset=2)[0] + page(client, limit=2, offset=4)[0] == expected
    assert page(client)[0] == expected


def test_case_list_offsets_shift_when_a_case_changes_between_requests(tmp_path, monkeypatch):
    store, ids = seed_cases(tmp_path, monkeypatch, minute_stamps(5) + ["2026-01-01T01:00:00+00:00"], count=5)
    client = list_client(tmp_path)
    assert page(client, limit=2)[0] == [ids[4], ids[3]]
    store.add_note(ids[0], "Moved to the top.")
    second, meta = page(client, limit=2, offset=2)
    assert second == [ids[3], ids[2]] and meta == {"total": 5, "limit": 2, "offset": 2, "has_more": True}
    assert page(client, limit=2)[0] == [ids[0], ids[4]]


@pytest.mark.parametrize("public_demo", [False, True])
def test_case_list_keeps_existing_fields(tmp_path, monkeypatch, public_demo):
    store, ids = seed_cases(tmp_path, monkeypatch, minute_stamps(3))
    body = list_client(tmp_path, public_demo).get("/api/cases", params={"limit": 2, "offset": 1}).json()
    assert set(body) == {"cases", "statuses", "transitions", "storage_note", "pagination"}
    assert body["statuses"] == STATUS_HELP
    assert body["transitions"] == {k: sorted(v) for k, v in TRANSITIONS.items()}
    assert body["storage_note"] == (PUBLIC_DEMO_NOTE if public_demo else None)
    assert body["cases"] == [store.get(ids[1]), store.get(ids[0])]
    assert body["pagination"] == {"total": 3, "limit": 2, "offset": 1, "has_more": False}


def test_case_list_pages_alongside_case_operations(client):
    events = client.get("/api/response/events", params={"kind": "rain"}).json()["events"]
    first = client.post("/api/cases", json={"area": "lucknow", "kind": "rain", "event_id": events[0]["id"]}).json()["id"]
    second = client.post("/api/cases", json={"area": "lucknow", "kind": "rain", "event_id": events[1]["id"]}).json()["id"]
    assert client.post("/api/cases", json={"area": "lucknow", "kind": "rain", "event_id": events[0]["id"]}).json()["id"] == first
    body = client.get("/api/cases", params={"limit": 1, "offset": 1}).json()
    assert body["pagination"] == {"total": 2, "limit": 1, "offset": 1, "has_more": False}
    assert client.post(f"/api/cases/{first}/status", json={"to": "investigating"}).json()["status"] == "investigating"
    assert client.post(f"/api/cases/{first}/notes", json={"text": "Checked the gauges."}).status_code == 200
    ids = [c["id"] for c in client.get("/api/cases").json()["cases"]]
    assert sorted(ids) == sorted([first, second]) and len(ids) == 2
    brief = client.get(f"/api/cases/{first}/brief")
    assert brief.status_code == 200 and "Checked the gauges." in brief.text
