from app.mapping.matcher import match_column, resolve_conflicts


def test_synonyms_premium():
    assert match_column("UMR", ["B0621XLS008832"], "premium")["canonical"] == "policy.unique_market_reference"
    assert match_column("On Risk Date", ["01/04/2026"], "premium")["canonical"] == "policy.inception_date"
    assert match_column("Our Line %", ["15"], "premium")["canonical"] == "premium.signed_line"
    assert match_column("Ccy", ["GBP"], "premium")["canonical"] == "premium.currency"


def test_claims_ccy_goes_to_claim_currency():
    assert match_column("Ccy", ["GBP"], "claims")["canonical"] == "claim.currency"
    assert match_column("O/S Reserve", ["1"], "claims")["canonical"] == "claim.outstanding"
    assert match_column("Cause of Loss", ["Fire damage to warehouse roof and storage area"], "claims")["canonical"] == "claim.description"


def test_notes_is_free_text():
    m = match_column("Notes", ["Endt 15/02/26 sprklr system installed prem adj -1200. See also POL"], "premium")
    assert m["canonical"] == "unmapped" and m.get("free_text")


def test_conflicts():
    ms = [{"source": "A", "canonical": "insured.name", "confidence": 90, "origin": "rule"},
          {"source": "B", "canonical": "insured.name", "confidence": 60, "origin": "rule"}]
    out = resolve_conflicts(ms)
    assert out[0]["canonical"] == "insured.name" and out[1]["canonical"] == "unmapped"


def test_status_in_claims_is_claim_status():
    assert match_column("Status", ["Open"], "claims")["canonical"] == "claim.status"
