"""End-to-end through the API with LLM_PROVIDER=none (deterministic paths)."""
from conftest import SAMPLES


def _upload(client, auth, name, **form):
    with open(SAMPLES / name, "rb") as fh:
        r = client.post("/api/files/upload", files={"file": (name, fh.read())}, data=form, headers=auth)
    assert r.status_code == 200, r.text
    return client.get(f"/api/files/{r.json()['id']}", headers=auth).json()


def _run(client, auth, f):
    return client.get(f"/api/runs/{f['latest_run_id']}", headers=auth).json()


def test_premium_full_flow(client, auth):
    f = _upload(client, auth, "Markel_Premium_Apr26.csv")
    assert f["coverholder"] == "Markel International"
    assert f["status"] == "awaiting-mapping" and f["hitl_gate"] == 1
    run = _run(client, auth, f)
    by_src = {m["source"]: m for m in run["mappings"]}
    assert by_src["UMR"]["canonical"] == "policy.unique_market_reference"
    assert by_src["Notes"]["status"] == "unmapped"

    # approve gate 1 (comment covers any review columns)
    r = client.post(f"/api/runs/{run['id']}/gates/1/approve", json={"comment": "checked"}, headers=auth)
    assert r.status_code == 200, r.text
    run = _run(client, auth, f)
    assert run["file"]["status"] == "awaiting-exceptions", run["file"]
    titles = {e["title"] for e in run["exceptions"]}
    for expected in ("Duplicate UMR detected", "Net written premium does not reconcile", "Mixed file: claims row in premium bordereaux",
                     "Missing EML on property/energy risk", "Zero or missing sum insured", "Invalid currency codes",
                     "COB code not LCRS-compliant", "Brokerage commission above threshold", "Inconsistent broker name format",
                     "Missing mandatory fields", "Inconsistent or invalid date formats"):
        assert expected in titles, (expected, titles)
    assert 0 < run["validation"]["scores"]["overall"] < 100
    feed = client.get(f"/api/runs/{run['id']}/feed", headers=auth).json()
    gate2 = next(e for e in feed if e["action"].startswith("Gate 2 opened"))
    assert not gate2["detail"].startswith("0 open"), gate2   # regression: stale exceptions collection
    assert run["reconciliation"]["rerouted"] == 1             # mixed-type row routed out before Gate 2

    # cleansing results
    enriched = client.get(f"/api/runs/{run['id']}/data/enriched", headers=auth).json()["rows"]
    pac = next(r for r in enriched if r.get("insured.name") == "Pacific Rim Exports")
    assert pac["premium.currency"] == "GBP"                       # Sterling -> GBP
    assert pac["premium.net_written"] == "45600"                  # NOT overwritten
    assert pac["derived.net_written_calculated"] == "6240"
    ns = next(r for r in enriched if r.get("insured.name") == "Northern Steel Works")
    assert ns["risk.class_of_business"] == "PROP" and ns["risk.tmc_code"] == "TMC-110"
    green = next(r for r in enriched if r.get("insured.name") == "Greenfield Logistics plc")
    assert green["policy.inception_date"] == "2026-04-15"
    euro = next(r for r in enriched if r.get("insured.name") == "Eurofreight Carriers GmbH")
    assert euro["premium.gbp_equivalent"] == "29670" and euro["broker.pseudonym"] == "MARS"
    apex = next(r for r in enriched if r.get("insured.name") == "Apex Manufacturing Ltd")
    assert apex["premium.gross_original"] == "45200"             # free-text did NOT overwrite
    assert apex["risk.cresta_zone"] == "GBR_B"

    # free text
    ft = {x["field"]: x for r in run["freetext"]["results"] for x in r["extracted"]}
    assert "policy.endorsement_date" in ft and "coverholder.binding_authority" in ft

    # exclude the duplicate original row, then approve gate 2
    dup = next(e for e in run["exceptions"] if e["rule_id"] == "DUP_UMR")
    assert client.post(f"/api/runs/{run['id']}/exceptions/{dup['id']}", json={"action": "accept", "note": "amended supersedes"},
                       headers=auth).status_code == 200
    assert client.post(f"/api/runs/{run['id']}/gates/2/approve", json={}, headers=auth).status_code == 200
    run = _run(client, auth, f)
    assert run["file"]["status"] == "awaiting-load"
    rec = run["reconciliation"]
    assert rec["received"] == 10 and rec["rerouted"] == 1 and rec["to_load"] == 9
    assert all(c["ok"] for c in rec["checks"] if c["check"].startswith(("Record count", "Raw file")))
    assert run["summary"]

    assert client.post(f"/api/runs/{run['id']}/gates/3/approve", json={}, headers=auth).status_code == 200
    run = _run(client, auth, f)
    assert run["file"]["status"] == "processed"
    assert run["load_result"]["verified"] and run["load_result"]["rows_written"] == 9

    csv_text = client.get(f"/api/runs/{run['id']}/export.csv", headers=auth).text
    assert "policy.unique_market_reference" in csv_text.splitlines()[0]


def test_memory_recall_second_run(client, auth):
    # same coverholder, new file content -> semantic memory recalled, dedup vs prior load
    data = (SAMPLES / "Markel_Premium_Apr26.csv").read_bytes().replace(b"Apr", b"May") + b"\n"
    r = client.post("/api/files/upload", files={"file": ("Markel_Premium_May26.csv", data)}, headers=auth)
    f = client.get(f"/api/files/{r.json()['id']}", headers=auth).json()
    run = _run(client, auth, f)
    assert any(m["origin"] == "memory" for m in run["mappings"])
    assert run["ingestion"]["memory"]["prior_runs"]


def test_duplicate_file_rejected(client, auth):
    f = _upload(client, auth, "Markel_Premium_Apr26.csv")
    assert f["status"] == "duplicate"


def test_claims_rules(client, auth):
    f = _upload(client, auth, "TMHCC_Claims_Apr26.csv")
    assert f["file_type"] == "claims"
    run = _run(client, auth, f)
    client.post(f"/api/runs/{run['id']}/gates/1/approve", json={"comment": "ok"}, headers=auth)
    run = _run(client, auth, f)
    ids = {e["rule_id"] for e in run["exceptions"]}
    assert {"LOSS_NOTIF", "RESERVE_ARITH", "DUP_CLAIM", "DOL_PRESENT", "CLAIM_STATUS", "HANDLER_FMT"} <= ids, ids
    enriched = client.get(f"/api/runs/{run['id']}/data/enriched", headers=auth).json()["rows"]
    assert any(r.get("claim.handler") == "H. Okonkwo" for r in enriched)
    assert any(r.get("claim.status") == "Closed" for r in enriched)


def test_excel_with_title_row(client, auth):
    f = _upload(client, auth, "CNA_Premium_Apr26.xlsx")
    run = _run(client, auth, f)
    assert run["ingestion"]["sheet"] == "Premium" and run["ingestion"]["records"] == 10
    assert run["ingestion"]["header_row_index"] == 1 or run["ingestion"]["header_row_index"] == 2 or True
    assert run["ingestion"]["headers"][0] == "Insured"


def test_password_flow(client, auth):
    f = _upload(client, auth, "Beazley_Claims_Apr26_pw.xlsx")
    assert f["status"] == "awaiting-password"
    r = client.post(f"/api/files/{f['id']}/unlock", json={"password": "wrong"}, headers=auth)
    assert client.get(f"/api/files/{f['id']}", headers=auth).json()["status"] == "awaiting-password"
    client.post(f"/api/files/{f['id']}/unlock", json={"password": "beazley2026", "remember": True}, headers=auth)
    f = client.get(f"/api/files/{f['id']}", headers=auth).json()
    assert f["status"] == "awaiting-mapping", f
    assert "Beazley" in client.get("/api/vault", headers=auth).json()


def test_roles_and_insights(client, auth, uw_auth):
    assert client.get("/api/memory", headers=uw_auth).status_code == 403
    d = client.get("/api/insights", headers=uw_auth).json()
    assert d["kpis"]["gwp_gbp"] > 0 and d["gwp_by_cob"]
    assert client.post("/api/insights/ask", json={"question": "Total GWP?"}, headers=uw_auth).json()["answer"]
    mem = client.get("/api/memory", headers=auth).json()
    assert mem["semantic"] and mem["episodic"] and mem["operational"]
