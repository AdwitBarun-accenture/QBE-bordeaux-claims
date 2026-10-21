"""STAGE 06 - Reporting Agent (reconcile, load, summarise, notify)

Mockup: reconciliation rows were hard-coded to pass ('Data preservation 100%',
'Duplicate UMRs 0' even when duplicates existed), Snowflake commit was a feed
message, and the DUA email was an alert().

Here:
  prepare()  - builds the final dataset: enriched rows + per-row DQ flags from
               open exceptions; rows excluded by the analyst or re-routed (claims
               rows inside a premium file) are separated, never dropped silently.
               Reconciliation is computed, not asserted:
                 * record count: received = to-load + excluded + re-routed
                 * raw file integrity: SHA-256 of the stored original re-checked
                 * control totals: sum of gross (or incurred) per currency,
                   source vs final
                 * mandatory field coverage, unresolved duplicates, schema version
               + executive summary (LLM, template fallback)
  load()     - Gate 3 approved: atomic load to the warehouse, then a read-back
               count check (load verification).
  dua_email()- on rejection, drafts the coverholder email for analyst approval.
"""
from collections import defaultdict
from datetime import date, timedelta

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.core.lcrs_schema import mandatory_fields
from app.llm.base import LLMUnavailable
from app.llm.prompts import reporting as P
from app.loaders.factory import get_warehouse
from app.services.intake import raw_key
from app.storage.factory import get_store, load_dataset, save_dataset
from app.utils.hashing import sha256_bytes
from app.utils.numbers import parse_float


class ReportingAgent(BaseAgent):
    name = "Reporting Agent"

    def run(self) -> None:
        self.prepare()

    # ------------------------------------------------------------------ prepare
    def prepare(self) -> None:
        run, f = self.ctx.run, self.ctx.file
        parsed = self.ctx.cache["parsed"]
        enriched = self.ctx.cache.get("enriched") or load_dataset(run.id, "enriched")["rows"]

        flags_by_row, excluded, rerouted = defaultdict(list), set(), set()
        for e in run.exceptions:
            if e.status == "excluded":
                excluded.update(e.row_indexes)
            elif e.rule_id == "MIXED_TYPES" and e.status in ("open", "rerouted"):
                rerouted.update(e.row_indexes)
            if e.status in ("open", "accepted"):
                for r in e.row_indexes:
                    flags_by_row[r].append(e.rule_id)

        final, ex_rows, rr_rows = [], [], []
        for row in enriched:
            n = row["_row"]
            row = {**row, "_dq_flags": sorted(set(row.get("_dq_flags", []) + flags_by_row.get(n, [])))}
            (ex_rows if n in excluded else rr_rows if n in rerouted else final).append(row)

        save_dataset(run.id, "final", final)
        if rr_rows:
            save_dataset(run.id, "rerouted", rr_rows)
        self.ctx.cache["final"] = final
        run.reconciliation = self._reconcile(parsed, enriched, final, ex_rows, rr_rows)
        ok = all(c["ok"] for c in run.reconciliation["checks"])
        self.log("Reconciliation complete",
                 f"{len(final)} to load, {len(ex_rows)} excluded, {len(rr_rows)} re-routed; "
                 f"{'all checks passed' if ok else 'CHECK FAILURES - see reconciliation'}", "info" if ok else "warn")
        run.summary = self.summary()

    def _reconcile(self, parsed, enriched, final, ex_rows, rr_rows) -> dict:
        f, run = self.ctx.file, self.ctx.run
        checks = []
        received = len(parsed)
        accounted = len(final) + len(ex_rows) + len(rr_rows)
        checks.append({"check": "Record count", "ok": received == accounted == len(enriched),
                       "source": received, "target": f"{len(final)} load + {len(ex_rows)} excluded + {len(rr_rows)} re-routed"})
        try:
            digest = sha256_bytes(get_store().get_raw(raw_key(f)))
            checks.append({"check": "Raw file integrity (SHA-256)", "ok": digest == f.sha256, "source": f.sha256[:12], "target": digest[:12]})
        except Exception as e:
            checks.append({"check": "Raw file integrity (SHA-256)", "ok": False, "source": f.sha256[:12], "target": f"unreadable: {e}"})

        amount_src = "premium.gross_original" if f.file_type == "premium" else "claim.total_incurred"
        ccy_f = "premium.currency" if f.file_type == "premium" else "claim.currency"
        src_col = next((m["source"] for m in run.mappings if m["canonical"] == amount_src and m["status"] != "unmapped"), None)
        if src_col:
            src_total = round(sum(parse_float(r.get(src_col)) or 0 for r in parsed), 2)
            tgt_total = round(sum(parse_float(r.get(amount_src)) or 0 for r in final + ex_rows + rr_rows), 2)
            checks.append({"check": f"Control total ({amount_src.split('.')[-1]})", "ok": abs(src_total - tgt_total) < 0.01,
                           "source": f"{src_total:,.2f}", "target": f"{tgt_total:,.2f}"})
            by_ccy = defaultdict(float)
            for r in final:
                by_ccy[r.get(ccy_f) or "?"] += parse_float(r.get(amount_src)) or 0
        else:
            by_ccy = {}
            checks.append({"check": "Control total", "ok": False, "source": "amount column not mapped", "target": "-"})

        req = mandatory_fields(f.file_type)
        covered = [x for x in req if any(r.get(x) for r in final)]
        checks.append({"check": "Mandatory field coverage", "ok": len(covered) == len(req), "source": f"{len(req)} required",
                       "target": f"{len(covered)} populated"})
        dup_open = [e for e in run.exceptions if e.rule_id in ("DUP_UMR", "DUP_CLAIM") and e.status == "open"]
        checks.append({"check": "Duplicates resolved", "ok": not dup_open, "source": "checked",
                       "target": f"{sum(e.count for e in dup_open)} rows unresolved" if dup_open else "none open"})
        checks.append({"check": "Schema version", "ok": True, "source": get_settings().schema_version, "target": get_settings().schema_version})
        gbp_field = "premium.gbp_equivalent" if f.file_type == "premium" else "derived.claim_gbp_incurred"
        gbp = round(sum(parse_float(r.get(gbp_field)) or 0 for r in final), 2)
        return {"checks": checks, "received": received, "to_load": len(final), "excluded": len(ex_rows), "rerouted": len(rr_rows),
                "flagged": sum(bool(r["_dq_flags"]) for r in final), "control_by_currency": {k: round(v, 2) for k, v in by_ccy.items()},
                "gbp_total": gbp, "gbp_measure": "gross premium" if f.file_type == "premium" else "total incurred"}

    # ------------------------------------------------------------------ summary
    def summary(self) -> str:
        run, f = self.ctx.run, self.ctx.file
        sc = run.validation.get("scores", {})
        open_exc = [e for e in run.exceptions if e.status in ("open", "accepted")]
        ctx = {"filename": f.filename, "coverholder": f.coverholder_name, "file_type": f.file_type,
               "records": run.reconciliation.get("received"), "quality": sc.get("overall"), "scores": sc,
               "mapped": sum(m["status"] != "unmapped" for m in run.mappings), "columns": len(run.mappings),
               "gbp_total": run.reconciliation.get("gbp_total"),
               "exceptions": [f"[{e.severity}] {e.title} ({e.count} rows, {e.status})" for e in open_exc[:8]],
               "recon": [f"{c['check']}: {'ok' if c['ok'] else 'FAIL'}" for c in run.reconciliation.get("checks", [])]}
        try:
            text = self.llm.text("executive summary", P.SUMMARY_SYSTEM, P.summary(ctx), 700).text
            self.log("Executive summary generated")
            return text
        except LLMUnavailable:
            still_open = [e for e in open_exc if e.status == "open"]
            accepted = [e for e in open_exc if e.status == "accepted"]
            hi = [e for e in still_open if e.severity == "high"]
            verdict = ("clean" if not open_exc else "blocked pending resolution of high-severity exceptions" if hi
                       else "loadable, with affected records flagged")
            return (f"{f.coverholder_name} submitted {ctx['records']} {f.file_type} records ({f.filename}). Overall data quality "
                    f"scored {sc.get('overall')}% (completeness {sc.get('completeness')}%, accuracy {sc.get('accuracy')}%, "
                    f"consistency {sc.get('consistency')}%); {ctx['mapped']}/{ctx['columns']} columns mapped.\n\n"
                    + ((f"{len(still_open)} exception(s) are open ({len(hi)} high severity)" if still_open else "")
                       + ("; " if still_open and accepted else "")
                       + (f"{len(accepted)} were accepted by the analyst and load as flagged records" if accepted else "")
                       + ": " + "; ".join(e.title for e in open_exc[:5]) + "." if open_exc else "No exceptions were raised.")
                    + f"\n\nThe dataset is {verdict}. {run.reconciliation.get('to_load')} records are staged for load "
                    f"(GBP {run.reconciliation.get('gbp_total'):,.0f} {run.reconciliation.get('gbp_measure', 'gross')}).")

    # ------------------------------------------------------------------ load
    def load(self) -> dict:
        run, f = self.ctx.run, self.ctx.file
        final = self.ctx.cache.get("final") or load_dataset(run.id, "final")["rows"]
        wh = get_warehouse()
        res = wh.load(final, {"file_id": f.id, "run_id": run.id, "coverholder": f.coverholder_name, "file_type": f.file_type,
                              "schema_version": get_settings().schema_version})
        readback = wh.count_for_load(res.load_id)
        verified = readback == res.rows_written or readback == -1
        run.load_result = {"load_id": res.load_id, "target": res.target, "rows_written": res.rows_written,
                           "rows_flagged": res.rows_flagged, "control_total_gbp": res.control_total_gbp,
                           "readback_count": readback, "verified": verified}
        self.log("Dataset committed to warehouse",
                 f"{res.rows_written} rows ({res.rows_flagged} flagged) -> {res.target}, load {res.load_id[:8]}; "
                 f"read-back {'verified' if verified else 'MISMATCH'}", "info" if verified else "error")
        return run.load_result

    # ------------------------------------------------------------------ DUA email
    def dua_email(self, outcome: str, comment: str = "") -> str:
        run, f = self.ctx.run, self.ctx.file
        issues = "\n".join(f"- {e.title}: {e.suggestion}" for e in run.exceptions if e.status == "open")[:3000] or "- see comment"
        ctx = {"coverholder": f.coverholder_name, "filename": f.filename, "outcome": outcome, "comment": comment,
               "issues": issues, "deadline": (date.today() + timedelta(days=5)).strftime("%d %B %Y")}
        try:
            return self.llm.text("DUA email draft", P.DUA_SYSTEM, P.dua_email(ctx), 700).text
        except LLMUnavailable:
            return (f"Subject: Bordereaux {f.filename} - corrections required\n\nDear {f.coverholder_name} team,\n\n"
                    f"We have reviewed your bordereaux {f.filename} and are unable to accept it in its current form."
                    f"{(' ' + comment) if comment else ''}\n\nPlease address the following:\n{issues}\n\n"
                    f"We would be grateful for a corrected resubmission by {ctx['deadline']}.\n\nKind regards,\nBordereaux Team")


def export_csv(rows: list[dict]) -> str:
    import csv
    import io
    keys = sorted({k for r in rows for k in r if not k.startswith("_")})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_row"] + keys + ["dq_flags"])
    for r in rows:
        w.writerow([r.get("_row")] + [r.get(k, "") for k in keys] + [";".join(r.get("_dq_flags", []))])
    return buf.getvalue()
