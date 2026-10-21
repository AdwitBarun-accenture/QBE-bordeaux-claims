"""Format normalisation steps (cleansing)."""
import re

from app.core.lcrs_schema import DType, FIELD_INDEX
from app.enrichment.base import Change, Step, StepContext
from app.rules.helpers import cob_lookup, currency_lookup
from app.utils.dates import parse_date
from app.utils.numbers import fmt_num, parse_decimal
from app.utils.reference import load_ref
from app.utils.text import clean_str, looks_like_email, normalise_header


class TrimWhitespace(Step):
    name, description = "Whitespace & control characters", "Trim and collapse whitespace on every value"

    def apply(self, row, ctx):
        ch = []
        for k in [k for k in row if not k.startswith("_")]:
            ch += self.set(row, k, clean_str(row[k]), self.name)
        return ch


class NumberNormalisation(Step):
    name, description = "Number normalisation", "'1,250,000', '2.5m', '(1,200)', '12.5%' -> plain numbers"

    def apply(self, row, ctx):
        ch = []
        for k in [k for k in row if not k.startswith("_")]:
            f = FIELD_INDEX.get(k)
            if f and f.dtype in (DType.DECIMAL, DType.PERCENT) and row[k] != "":
                d = parse_decimal(row[k])
                if d is not None:
                    ch += self.set(row, k, fmt_num(d, 6), self.name)
        return ch


class DateNormalisation(Step):
    name, description = "Date normalisation", "DD/MM/YYYY, MM/DD/YYYY, text and Excel dates -> ISO 8601"

    def apply(self, row, ctx):
        ch = []
        for k in [k for k in row if not k.startswith("_")]:
            f = FIELD_INDEX.get(k)
            if f and f.dtype == DType.DATE and row[k]:
                p = parse_date(row[k], ctx.date_order)
                if p.value:
                    ch += self.set(row, k, p.iso, self.name)
                else:
                    row.setdefault("_dq_flags", []).append(f"UNPARSEABLE_DATE:{k}")
        return ch


class CurrencyNormalisation(Step):
    name, description = "Currency normalisation", "Aliases such as 'Sterling' -> ISO 4217 'GBP'"

    def apply(self, row, ctx):
        ch = []
        for k in ("premium.currency", "claim.currency"):
            if row.get(k):
                iso = currency_lookup(row[k])
                if iso:
                    ch += self.set(row, k, iso, self.name)
        return ch


class CountryNormalisation(Step):
    name, description = "Country normalisation", "Country names -> ISO 3166 alpha-2"

    def apply(self, row, ctx):
        ref, ch = load_ref("countries"), []
        for k in ("risk.country", "insured.country"):
            v = row.get(k, "")
            if v and v.upper() not in ref["iso2"] and v.lower() in ref["aliases"]:
                ch += self.set(row, k, ref["aliases"][v.lower()], self.name)
            elif v and v.upper() in ref["iso2"]:
                ch += self.set(row, k, v.upper(), self.name)
        return ch


class CobNormalisation(Step):
    name, description, applies_to = "COB code normalisation", "'Property' -> PROP, 'Liability' -> LIAB", ("premium",)

    def apply(self, row, ctx):
        v = row.get("risk.class_of_business", "")
        code = cob_lookup(v) if v else None
        return self.set(row, "risk.class_of_business", code, self.name) if code else []


class BrokerNormalisation(Step):
    name, description = "Broker normalisation", "Broker name variants -> canonical name; derive missing pseudonym"

    def apply(self, row, ctx):
        raw = row.get("broker.name", "")
        if not raw:
            return []
        aliases = load_ref("broker_aliases")
        key = normalise_header(raw)
        for code, meta in aliases.items():
            if key in meta["aliases"]:
                ch = self.set(row, "broker.name", meta["name"], self.name)
                if not row.get("broker.pseudonym"):
                    ch += self.set(row, "broker.pseudonym", code, self.name + " (derived code)")
                return ch
        return []


class ClaimStatusNormalisation(Step):
    name, description, applies_to = "Claim status normalisation", "'Settled' -> Closed per LCRS status list", ("claims",)

    def apply(self, row, ctx):
        v = row.get("claim.status", "")
        mapped = load_ref("claim_status")["aliases"].get(v.lower()) if v else None
        return self.set(row, "claim.status", mapped, self.name) if mapped else []


class HandlerNormalisation(Step):
    name, description, applies_to = "Handler normalisation", "Email addresses in handler -> 'H. Okonkwo'", ("claims",)

    def apply(self, row, ctx):
        v = row.get("claim.handler", "")
        if not looks_like_email(v):
            return []
        local = v.split("@")[0]
        parts = [p for p in re.split(r"[._-]", local) if p]
        name = (parts[0][0].upper() + ". " + " ".join(p.capitalize() for p in parts[1:])) if len(parts) > 1 else local.capitalize()
        return self.set(row, "claim.handler", name, self.name)


class CoverholderFill(Step):
    name, description = "Coverholder stamp", "Populate coverholder.name from the file's coverholder"

    def apply(self, row, ctx):
        return [] if row.get("coverholder.name") or not ctx.coverholder else self.set(row, "coverholder.name", ctx.coverholder, self.name)
