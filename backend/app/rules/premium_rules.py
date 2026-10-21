import re
from collections import defaultdict

from app.rules.base import Rule, RuleContext, register, rows_ref
from app.rules.helpers import blank, cob_lookup, currency_lookup, dt, num, val
from app.utils.numbers import approx_equal
from app.utils.reference import load_ref
from app.utils.text import normalise_header

P = ("premium",)


@register
class InceptionBeforeExpiry(Rule):
    id, name, severity, dimension, applies_to = "INC_EXP", "Inception before expiry", "error", "consistency", P
    requires = ("policy.inception_date", "policy.expiry_date")

    def check(self, ctx: RuleContext):
        bad = []
        for r in ctx.rows:
            i, e = dt(r, "policy.inception_date", ctx.date_order), dt(r, "policy.expiry_date", ctx.date_order)
            if i.value and e.value and i.value >= e.value:
                bad.append(r["_row"])
        return self.result(bad, f"Inception on/after expiry on {rows_ref(bad)}", "All date ranges valid",
                           "Inception date after expiry date", "Obtain corrected policy period from the coverholder.")


@register
class DuplicateUmr(Rule):
    id, name, severity, dimension, applies_to = "DUP_UMR", "Duplicate UMR check", "error", "consistency", P
    requires = ("policy.unique_market_reference",)

    def check(self, ctx):
        seen = defaultdict(list)
        for r in ctx.rows:
            u = val(r, "policy.unique_market_reference").upper()
            ref = val(r, "policy.reference").upper()
            if u:
                seen[(u, ref)].append(r["_row"])
        dups = {k: v for k, v in seen.items() if len(v) > 1}
        failing = [n for v in dups.values() for n in v]
        detail = "; ".join(f"{k[0]} on rows {', '.join(map(str, v))}" for k, v in dups.items())
        return self.result(failing, detail, "No duplicate UMRs", "Duplicate UMR detected",
                           "Likely an amended record submitted alongside the original - confirm which supersedes and drop the other.")


@register
class PriorSubmissionDedup(Rule):
    id, name, severity, dimension, applies_to = "DUP_PRIOR", "UMR already loaded in a prior submission", "warning", "consistency", P
    requires = ("policy.unique_market_reference",)

    def check(self, ctx):
        if not ctx.settings["processing"]["dedup_check"]:
            return self.skipped("dedup check disabled in settings")
        bad = [r["_row"] for r in ctx.rows if val(r, "policy.unique_market_reference").upper() in ctx.prior_umrs]
        return self.result(bad, f"UMRs on {rows_ref(bad)} were loaded in an earlier bordereaux", "No overlap with prior submissions",
                           "Records repeat a prior submission",
                           "Confirm whether these are endorsements/adjustments or genuine duplicates before loading.")


@register
class SignedLineArithmetic(Rule):
    id, name, severity, dimension, applies_to = "NET_ARITH", "Net written = gross x signed line", "error", "accuracy", P
    requires = ("premium.gross_original", "premium.net_written", "premium.signed_line")

    def check(self, ctx):
        bad, notes = [], []
        for r in ctx.rows:
            g, n, l = num(r, "premium.gross_original"), num(r, "premium.net_written"), num(r, "premium.signed_line")
            if None in (g, n, l):
                continue
            exp = g * l / 100
            if not approx_equal(n, exp):
                bad.append(r["_row"])
                notes.append(f"row {r['_row']}: stated {n:,.0f} vs {g:,.0f} x {l:g}% = {exp:,.0f}")
        return self.result(bad, "; ".join(notes[:5]), "All net written figures reconcile",
                           "Net written premium does not reconcile",
                           "Obtain the corrected net written figure (or signed line) from the coverholder.")


@register
class EmlOnProperty(Rule):
    id, name, severity, dimension, applies_to = "EML_PROP", "EML present on property/energy risks", "warning", "completeness", P
    requires = ("risk.class_of_business",)

    def check(self, ctx):
        need = set(load_ref("cob_codes")["requires_eml"])
        bad = [r["_row"] for r in ctx.rows if cob_lookup(val(r, "risk.class_of_business")) in need and blank(r, "risk.eml_percent")]
        return self.result(bad, f"EML missing on {rows_ref(bad)}", "All property/energy risks have EML",
                           "Missing EML on property/energy risk", "EML is mandatory for PROP/ENGY - request it from the coverholder.")


@register
class SumInsuredPresent(Rule):
    id, name, severity, dimension, applies_to = "SI_PRESENT", "Sum insured declared and non-zero", "error", "completeness", P

    def check(self, ctx):
        if "risk.sum_insured" not in ctx.mapped_fields:
            return self.skipped("risk.sum_insured not mapped")
        markers = load_ref("cob_codes")["claim_markers"]
        bad = [r["_row"] for r in ctx.rows
               if val(r, "risk.class_of_business").lower() not in markers and (num(r, "risk.sum_insured") or 0) <= 0]
        return self.result(bad, f"Blank/zero sum insured on {rows_ref(bad)}", "All risks declare a sum insured",
                           "Zero or missing sum insured", "Confirm sum insured with the coverholder before load.")


@register
class CobCodeValid(Rule):
    id, name, severity, dimension, applies_to = "COB_CODE", "Class of business in LCRS taxonomy", "warning", "accuracy", P
    requires = ("risk.class_of_business",)

    def check(self, ctx):
        codes = set(load_ref("cob_codes")["codes"])
        markers = load_ref("cob_codes")["claim_markers"]
        bad, notes = [], []
        for r in ctx.rows:
            raw = val(r, "risk.class_of_business")
            if not raw or raw.upper() in codes or raw.lower() in markers:
                continue
            bad.append(r["_row"])
            fix = cob_lookup(raw)
            notes.append(f"'{raw}' (row {r['_row']})" + (f" -> {fix}" if fix else " unrecognised"))
        return self.result(bad, "; ".join(notes[:6]), "All COB codes LCRS-compliant", "COB code not LCRS-compliant",
                           "Known aliases are normalised in cleansing; unrecognised classes need underwriter confirmation.")


@register
class MixedRecordTypes(Rule):
    id, name, severity, dimension, applies_to = "MIXED_TYPES", "Mixed record types (claims in premium file)", "error", "consistency", P
    CLAIM_REF = re.compile(r"^CLM[-/ ]?\d", re.I)

    def check(self, ctx):
        markers = load_ref("cob_codes")["claim_markers"]
        bad = [r["_row"] for r in ctx.rows
               if val(r, "risk.class_of_business").lower() in markers or self.CLAIM_REF.match(val(r, "policy.reference"))]
        return self.result(bad, f"Claims record(s) on {rows_ref(bad)} of a premium bordereaux", "Single record type",
                           "Mixed file: claims row in premium bordereaux",
                           "Extract these rows and route them to claims processing; exclude from the premium load.")


@register
class BrokerageCap(Rule):
    id, name, severity, dimension, applies_to = "BRKG_CAP", "Brokerage within cap", "info", "accuracy", P
    requires = ("premium.brokerage",)

    def check(self, ctx):
        cap = float(ctx.settings.get("brokerage_cap_percent", 15))
        bad = [r["_row"] for r in ctx.rows if (num(r, "premium.brokerage") or 0) > cap]
        return self.result(bad, f"Brokerage above {cap:g}% on {rows_ref(bad)}", f"All brokerage <= {cap:g}%",
                           "Brokerage commission above threshold", "Confirm the commission rate with the underwriter.")


@register
class PercentRanges(Rule):
    id, name, severity, dimension, applies_to = "PCT_RANGE", "Percentages within 0-100", "error", "accuracy", P

    def check(self, ctx):
        fields = [f for f in ("premium.signed_line", "risk.eml_percent", "premium.brokerage", "premium.expense_ratio") if f in ctx.mapped_fields]
        if not fields:
            return self.skipped("no percentage fields mapped")
        bad = [r["_row"] for r in ctx.rows for f in fields if (v := num(r, f)) is not None and not (0 <= v <= 100)]
        return self.result(bad, f"Out-of-range percentage on {rows_ref(bad)}", "All percentages within range",
                           "Percentage out of range", "Check whether the value was keyed as a decimal or an amount.")


@register
class PremiumNumeric(Rule):
    id, name, severity, dimension, applies_to = "PREM_NUM", "Premium amounts numeric", "error", "accuracy", P
    requires = ("premium.gross_original",)

    def check(self, ctx):
        bad = [r["_row"] for r in ctx.rows if not blank(r, "premium.gross_original") and num(r, "premium.gross_original") is None]
        return self.result(bad, f"Non-numeric gross premium on {rows_ref(bad)}", "All premium amounts numeric",
                           "Non-numeric premium", "Correct the premium value format.")


@register
class BrokerPseudonymPresent(Rule):
    id, name, severity, dimension, applies_to = "BKR_CODE", "Broker pseudonym present", "warning", "completeness", P
    requires = ("broker.pseudonym",)

    def check(self, ctx):
        bad = [r["_row"] for r in ctx.rows if blank(r, "broker.pseudonym")]
        return self.result(bad, f"Blank broker code on {rows_ref(bad)}", "All rows have a broker code",
                           "Missing broker pseudonym", "Derived from broker name in cleansing where known; otherwise request it.")


@register
class BrokerNameConsistency(Rule):
    id, name, severity, dimension, applies_to = "BKR_NAME", "Broker name format consistency", "info", "consistency", P
    requires = ("broker.name",)

    def check(self, ctx):
        aliases = load_ref("broker_aliases")
        groups = defaultdict(set)
        rows_by = defaultdict(list)
        for r in ctx.rows:
            raw = val(r, "broker.name")
            if not raw:
                continue
            key = next((code for code, m in aliases.items() if normalise_header(raw) in m["aliases"]), normalise_header(raw))
            groups[key].add(raw)
            rows_by[key].append(r["_row"])
        bad_keys = [k for k, v in groups.items() if len(v) > 1]
        failing = [n for k in bad_keys for n in rows_by[k]]
        detail = "; ".join(" / ".join(sorted(groups[k])) + f" -> {k}" for k in bad_keys)
        return self.result(failing, detail, "Broker names consistent", "Inconsistent broker name format",
                           "Normalised to the canonical broker pseudonym in cleansing.")


@register
class DaLimitProximity(Rule):
    id, name, severity, dimension, applies_to = "DA_LIMIT", "Delegated authority limit proximity", "warning", "accuracy", P
    requires = ("premium.gross_original",)

    def check(self, ctx):
        limit = float(ctx.coverholder.get("da_limit_gbp") or 0)
        if not limit:
            return self.skipped("no DA limit on coverholder profile")
        fx = load_ref("fx_rates")["rates"]
        file_gbp = 0.0
        for r in ctx.rows:
            g = num(r, "premium.gross_original") or 0
            ccy = currency_lookup(val(r, "premium.currency")) or "GBP"
            file_gbp += g * fx.get(ccy, 1.0)
        used = ctx.prior_written_gbp + file_gbp
        pct = used / limit * 100
        alert, watch = ctx.settings["da_alert_percent"], ctx.settings["da_watch_percent"]
        failing = [r["_row"] for r in ctx.rows] if pct >= alert else []
        res = self.result(failing, f"DA utilisation {pct:.0f}% (GBP {used:,.0f} of {limit:,.0f}) - at/above {alert:g}% alert",
                          f"DA utilisation {pct:.0f}% of GBP {limit:,.0f}", "Delegated authority limit approaching",
                          "Notify the underwriter; further binding may breach the binding authority.")
        if not failing and pct >= watch:
            res.detail += f" - on watch (>= {watch:g}%)"
        return res
