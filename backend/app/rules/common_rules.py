from app.core.lcrs_schema import DType, FIELD_INDEX, mandatory_fields
from app.rules.base import Rule, RuleContext, register, rows_ref
from app.rules.helpers import blank, currency_lookup, dt, val
from app.utils.reference import load_ref

DEDICATED_PRESENCE_RULES = {"claim.date_of_loss"}


@register
class MandatoryFields(Rule):
    id, name, severity, dimension = "MANDATORY", "Mandatory fields present", "error", "completeness"

    def check(self, ctx: RuleContext):
        req = [f for f in mandatory_fields(ctx.file_type) if f not in DEDICATED_PRESENCE_RULES]
        unmapped = [f for f in req if f not in ctx.mapped_fields]
        failing, by_field = [], {}
        for r in ctx.rows:
            missing = [f for f in req if blank(r, f)]
            if missing:
                failing.append(r["_row"])
                for f in missing:
                    by_field.setdefault(f, []).append(r["_row"])
        parts = [f"{f.split('.')[-1]} missing on {rows_ref(rs)}" for f, rs in by_field.items() if f not in unmapped]
        if unmapped:
            parts.insert(0, f"not mapped: {', '.join(unmapped)}")
        return self.result(failing, "; ".join(parts), "All mandatory LCRS fields populated",
                           "Missing mandatory fields",
                           "Request the missing values from the coverholder or map the source column at Gate 1.")


@register
class CurrencyIso(Rule):
    id, name, severity, dimension = "CCY_ISO", "Currency code validation (ISO 4217)", "warning", "accuracy"

    def check(self, ctx):
        field = "premium.currency" if ctx.file_type == "premium" else "claim.currency"
        if field not in ctx.mapped_fields:
            return self.skipped(f"{field} not mapped")
        iso = set(load_ref("currencies")["iso"])
        bad = [(r["_row"], val(r, field)) for r in ctx.rows if not blank(r, field) and val(r, field).upper() not in iso]
        fixable = [v for _, v in bad if currency_lookup(v)]
        detail = "; ".join(f"'{v}' on row {n}" + (f" -> {currency_lookup(v)}" if currency_lookup(v) else "") for n, v in bad[:5])
        return self.result([n for n, _ in bad], f"Non-ISO currency values: {detail}", "All currency codes ISO 4217 compliant",
                           "Invalid currency codes",
                           "Normalise to ISO 4217 (auto-fixed in cleansing where an alias is known); otherwise query the coverholder."
                           if len(fixable) == len(bad) else "Unknown currency values must be confirmed by the coverholder.")


@register
class DateFormatConsistency(Rule):
    id, name, severity, dimension = "DATE_FORMAT", "Date format consistency", "warning", "consistency"

    def check(self, ctx):
        date_fields = [f for f in ctx.mapped_fields if FIELD_INDEX.get(f) and FIELD_INDEX[f].dtype == DType.DATE]
        if not date_fields:
            return self.skipped("no date fields mapped")
        parsed = [(r, f, dt(r, f, ctx.date_order)) for r in ctx.rows for f in date_fields]
        other = "mdy" if ctx.date_order == "dmy" else "dmy"
        # A day/month-ambiguous value (01/04/2026) is fine when the coverholder's
        # date order is known AND the file contains no dates that unambiguously
        # use the other order. Once the file is mixed, ambiguous rows are uncertain.
        mixed = any(p.fmt == other and not p.ambiguous for _, _, p in parsed)
        trust_ambiguous = ctx.date_order_source == "profile" and not mixed
        failing, notes, formats = [], [], set()
        for r, f, p in parsed:
            if p.fmt == "blank":
                continue
            formats.add(p.fmt)
            if p.fmt in (other, "year_only", "invalid") or (p.ambiguous and not trust_ambiguous):
                failing.append(r["_row"])
                notes.append(f"row {r['_row']} {f.split('.')[-1]}: {p.note or p.fmt}")
        return self.result(failing, "; ".join(notes[:6]) + (f" (formats seen: {', '.join(sorted(formats))})" if formats else ""),
                           "All dates in a consistent, unambiguous format", "Inconsistent or invalid date formats",
                           "US-ordered dates are converted in cleansing; year-only or invalid dates need corrected values from the coverholder.")


@register
class CountryCode(Rule):
    id, name, severity, dimension = "COUNTRY", "Country code validation", "info", "accuracy"

    def check(self, ctx):
        fields = [f for f in ("risk.country", "insured.country") if f in ctx.mapped_fields]
        if not fields:
            return self.skipped("no country field mapped")
        ref = load_ref("countries")
        bad = [r["_row"] for r in ctx.rows for f in fields
               if not blank(r, f) and val(r, f).upper() not in ref["iso2"] and val(r, f).lower() not in ref["aliases"]]
        return self.result(bad, f"Unrecognised country values on {rows_ref(bad)}", "All countries recognised",
                           "Unrecognised country codes", "Map to ISO 3166 alpha-2 codes.")
