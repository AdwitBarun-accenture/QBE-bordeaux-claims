"""STAGE 04 - Cleansing, Normalisation & Enrichment Agent

(The mockup credits this stage to the 'Mapping Agent'; it is a separate agent
here because it has a separate job and its own audit trail.)

Mockup steps and what they actually did:
  Date normalisation      - only split on '/' assuming DD/MM; US dates broke silently
  FX normalisation        - hard-coded USD 0.79 / EUR 0.86; 'Sterling' fell back to 1.0
  TMC code enrichment     - PROP->TMC-110 ... (placeholder codes), raw 'Property' -> TMC-999
  Subscription share      - OVERWROTE stated net written with gross x line, hiding errors
  CRESTA zones            - label only, not implemented
  Expense allocation      - label only, not implemented

Here (enrichment/pipeline.py, 15 ordered steps, all with value-level lineage):
  whitespace -> numbers -> dates (ISO, file-level DMY/MDY detection) -> currency
  -> country -> COB -> broker -> claim status -> handler -> coverholder stamp
  -> FX to GBP -> TMC code -> subscription share (fill-blank only + calculated
  net kept separately) -> CRESTA (postcode -> zone) -> expense/brokerage amounts
"""
import copy

from app.agents.base import BaseAgent
from app.enrichment.base import StepContext
from app.enrichment.pipeline import run_steps
from app.storage.factory import save_dataset


class CleansingAgent(BaseAgent):
    name = "Cleansing Agent"

    def run(self) -> None:
        run, f = self.ctx.run, self.ctx.file
        rows = copy.deepcopy(self.ctx.cache["canonical"])
        sctx = StepContext(file_type=f.file_type, date_order=run.validation.get("date_order", "dmy"),
                           coverholder=f.coverholder_name)
        rows, lineage, summary = run_steps(rows, sctx)
        self.ctx.cache["enriched"] = rows
        save_dataset(run.id, "enriched", rows)
        save_dataset(run.id, "lineage", lineage)
        fields = sorted({k for r in rows for k in r if not k.startswith("_")})
        run.enrichment = {"steps": summary, "changes": len(lineage), "fields": len(fields),
                          "lineage_sample": lineage[:200], "dq_flagged_rows": sum(bool(r.get("_dq_flags")) for r in rows)}
        for s in summary:
            if s["changes"]:
                self.log(s["step"], f"{s['changes']} value(s) changed")
        self.log("Cleansing complete", f"{len(rows)} records, {len(fields)} fields, {len(lineage)} value changes with lineage")
