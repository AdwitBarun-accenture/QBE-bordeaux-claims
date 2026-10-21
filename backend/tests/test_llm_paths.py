"""Exercise the AI code paths with a fake provider (no network)."""
import json

from app.llm import client as llm_client
from app.llm.base import LLMProvider, LLMResponse
from app.llm.prompts import freetext, mapping, validation


class FakeProvider(LLMProvider):
    name = "fake"

    def complete(self, system, user, max_tokens=1500, temperature=0.0):
        if system == mapping.SYSTEM:
            out = [{"source": "Exp Ratio", "canonical": "premium.expense_ratio", "confidence": 92, "notes": "expense"}]
        elif system == validation.SYSTEM:
            out = {"findings": [{"title": "Unusually high premium rate", "severity": "low", "rows": [5], "suggestion": "Check rate"}]}
        elif system == freetext.SYSTEM:
            out = [{"row": 1, "extracted": [{"field": "risk.description", "value": "Sprinkler system installed",
                                             "confidence": 90, "source_phrase": "sprklr system installed", "kind": "flag"}]}]
        else:
            return LLMResponse("Plain text answer.", "fake", 10, 5)
        return LLMResponse("```json\n" + json.dumps(out) + "\n```", "fake", 100, 50)


def test_ai_paths(client, auth, monkeypatch):
    monkeypatch.setattr(llm_client, "get_provider", lambda: FakeProvider())
    data = b"Insured,UMR,Gross Prem,Ccy,Class,On Risk Date,Off Risk Date,Exp Ratio,Notes\n" \
           b"Apex,B0621XLS999001,1000,GBP,PROP,01/04/2026,31/03/2027,28,Endt 15/02/26 sprklr system installed prem adj -100\n" \
           b"B Co,B0621XLS999002,2000,GBP,PROP,01/04/2026,31/03/2027,20,\n" * 1
    r = client.post("/api/files/upload", files={"file": ("Hiscox_Premium_Test.csv", data)}, headers=auth)
    f = client.get(f"/api/files/{r.json()['id']}", headers=auth).json()
    run = client.get(f"/api/runs/{f['latest_run_id']}", headers=auth).json()
    client.post(f"/api/runs/{run['id']}/gates/1/approve", json={"comment": "ok"}, headers=auth)
    run = client.get(f"/api/runs/{f['latest_run_id']}", headers=auth).json()
    assert any(e["source"] == "ai" for e in run["exceptions"])
    assert run["summary"] == "Plain text answer."
    methods = {x["method"] for r in run["freetext"]["results"] for x in r["extracted"]}
    assert "ai" in methods and "rule" in methods
    feed = client.get(f"/api/runs/{run['id']}/feed", headers=auth).json()
    assert any(e["tokens"] > 0 for e in feed)
