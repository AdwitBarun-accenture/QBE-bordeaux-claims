"""Business enrichment steps."""
import re

from app.enrichment.base import Step
from app.utils.numbers import fmt_num, parse_float
from app.utils.reference import load_ref

UK_POSTCODE = re.compile(r"\b([A-Z]{1,2})\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)


class TmcCode(Step):
    name, description, applies_to = "TMC risk code enrichment", "Class of business -> risk code taxonomy", ("premium",)

    def apply(self, row, ctx):
        cob = row.get("risk.class_of_business")
        if not cob:
            return []
        ref = load_ref("tmc_codes")
        return self.set(row, "risk.tmc_code", ref["map"].get(cob, ref["unknown"]), self.name)


class SubscriptionShare(Step):
    name, description, applies_to = "Subscription share arithmetic", "Signed line % -> share; gross x line = calculated net", ("premium",)

    def apply(self, row, ctx):
        ch = []
        line, gross = parse_float(row.get("premium.signed_line")), parse_float(row.get("premium.gross_original"))
        if line is not None:
            ch += self.set(row, "premium.subscription_share", fmt_num(line, 4), self.name)
        if line is not None and gross is not None:
            calc = gross * line / 100
            ch += self.set(row, "derived.net_written_calculated", fmt_num(calc, 2), self.name)
            # Fill only when blank. A stated value that disagrees is a validation
            # exception, never silently overwritten (the mockup overwrote it).
            if not row.get("premium.net_written"):
                ch += self.set(row, "premium.net_written", fmt_num(calc, 2), self.name + " (filled blank)")
        return ch


class CrestaZone(Step):
    name, description, applies_to = "CRESTA zone assignment", "Risk postcode -> CRESTA zone (sample table; use a geocoder in prod)", ("premium",)

    def apply(self, row, ctx):
        ch = []
        addr = " ".join(filter(None, [row.get("risk.postcode", ""), row.get("risk.address", "")]))
        m = UK_POSTCODE.search(addr)
        if m and not row.get("risk.postcode"):
            ch += self.set(row, "risk.postcode", m.group(0).upper(), self.name)
        country = (row.get("risk.country") or "").upper()
        ref = load_ref("cresta_zones_sample")
        zone = ref.get(country, {}).get(m.group(1).upper()) if m else None
        return ch + self.set(row, "risk.cresta_zone", zone or ref["default"], self.name)


class ExpenseAllocation(Step):
    name, description, applies_to = "Expense allocation", "Brokerage % and expense ratio -> amounts per record", ("premium",)

    def apply(self, row, ctx):
        ch = []
        g = parse_float(row.get("premium.gross_original"))
        if g is None:
            return ch
        if (b := parse_float(row.get("premium.brokerage"))) is not None:
            ch += self.set(row, "derived.brokerage_amount", fmt_num(g * b / 100, 2), self.name)
        if (e := parse_float(row.get("premium.expense_ratio"))) is not None:
            ch += self.set(row, "derived.expense_amount", fmt_num(g * e / 100, 2), self.name)
        return ch
