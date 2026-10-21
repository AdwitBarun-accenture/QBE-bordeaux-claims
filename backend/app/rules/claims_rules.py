from collections import defaultdict
from datetime import date

from app.rules.base import Rule, RuleContext, register, rows_ref
from app.rules.helpers import blank, dt, num, val
from app.utils.numbers import approx_equal
from app.utils.reference import load_ref
from app.utils.text import looks_like_email

C = ("claims",)


@register
class LossBeforeNotification(Rule):
    id, name, severity, dimension, applies_to = "LOSS_NOTIF", "Loss date before notification date", "error", "consistency", C
    requires = ("claim.date_of_loss", "claim.date_reported")

    def check(self, ctx: RuleContext):
        bad, notes = [], []
        for r in ctx.rows:
            l, n = dt(r, "claim.date_of_loss", ctx.date_order), dt(r, "claim.date_reported", ctx.date_order)
            if l.value and n.value and l.value > n.value:
                bad.append(r["_row"])
                notes.append(f"row {r['_row']}: loss {l.iso} after notified {n.iso}")
        return self.result(bad, "; ".join(notes), "All losses precede notification", "Loss date after notification date",
                           "Chronologically impossible - request corrected dates from the coverholder/TPA.")


@register
class LossDateNotFuture(Rule):
    id, name, severity, dimension, applies_to = "LOSS_FUTURE", "Loss date not in the future", "error", "accuracy", C
    requires = ("claim.date_of_loss",)

    def check(self, ctx):
        today = date.today()
        bad = [r["_row"] for r in ctx.rows if (p := dt(r, "claim.date_of_loss", ctx.date_order)).value and p.value > today]
        return self.result(bad, f"Future loss date on {rows_ref(bad)}", "No future loss dates", "Loss date in the future",
                           "Correct the date of loss.")


@register
class ReserveArithmetic(Rule):
    id, name, severity, dimension, applies_to = "RESERVE_ARITH", "Paid + outstanding = total incurred", "error", "accuracy", C
    requires = ("claim.paid_to_date", "claim.outstanding", "claim.total_incurred")

    def check(self, ctx):
        bad, notes = [], []
        for r in ctx.rows:
            p, o, t = num(r, "claim.paid_to_date"), num(r, "claim.outstanding"), num(r, "claim.total_incurred")
            if None in (p, o, t):
                continue
            if not approx_equal(p + o, t, rel_tol=0.001):
                bad.append(r["_row"])
                notes.append(f"row {r['_row']}: {p:,.0f} + {o:,.0f} = {p+o:,.0f} vs incurred {t:,.0f}")
        return self.result(bad, "; ".join(notes), "Reserve arithmetic reconciles",
                           "Paid + outstanding does not equal total incurred",
                           "Reserve arithmetic error - obtain corrected figures from the TPA.")


@register
class DuplicateClaimRef(Rule):
    id, name, severity, dimension, applies_to = "DUP_CLAIM", "Duplicate claim references", "error", "consistency", C
    requires = ("claim.reference",)

    def check(self, ctx):
        seen = defaultdict(list)
        for r in ctx.rows:
            if (ref := val(r, "claim.reference").upper()):
                seen[ref].append(r)
        notes, failing = [], []
        for ref, rs in seen.items():
            if len(rs) > 1:
                failing += [x["_row"] for x in rs]
                reserves = {val(x, "claim.reserve_gross") or val(x, "claim.total_incurred") for x in rs}
                notes.append(f"{ref} on rows {', '.join(str(x['_row']) for x in rs)}"
                             + (f" with different reserves ({', '.join(sorted(reserves))})" if len(reserves) > 1 else ""))
        return self.result(failing, "; ".join(notes), "No duplicate claim references",
                           "Duplicate claim reference", "Likely a revised reserve - keep the latest movement and remove the superseded row.")


@register
class DateOfLossPresent(Rule):
    id, name, severity, dimension, applies_to = "DOL_PRESENT", "Date of loss present", "warning", "completeness", C

    def check(self, ctx):
        if "claim.date_of_loss" not in ctx.mapped_fields:
            return self.result([r["_row"] for r in ctx.rows], "Date of loss column not mapped", "", "Missing date of loss",
                               "Map the date-of-loss column or request it.")
        bad = [r["_row"] for r in ctx.rows if blank(r, "claim.date_of_loss")]
        return self.result(bad, f"Missing date of loss on {rows_ref(bad)}", "All claims have a date of loss",
                           "Missing date of loss", "Date of loss is mandatory - request it from the TPA.")


@register
class ClaimStatusTaxonomy(Rule):
    id, name, severity, dimension, applies_to = "CLAIM_STATUS", "Claim status in LCRS taxonomy", "info", "accuracy", C
    requires = ("claim.status",)

    def check(self, ctx):
        allowed = set(load_ref("claim_status")["allowed"])
        aliases = load_ref("claim_status")["aliases"]
        bad, notes = [], []
        for r in ctx.rows:
            s = val(r, "claim.status")
            if s and s not in allowed:
                bad.append(r["_row"])
                notes.append(f"'{s}'" + (f" -> {aliases[s.lower()]}" if s.lower() in aliases else " unknown"))
        return self.result(bad, "; ".join(sorted(set(notes))), "All statuses valid", "Non-standard claim status value",
                           "Normalised to the LCRS status list in cleansing.")


@register
class HandlerFormat(Rule):
    id, name, severity, dimension, applies_to = "HANDLER_FMT", "Handler recorded as a name", "info", "accuracy", C
    requires = ("claim.handler",)

    def check(self, ctx):
        bad = [r["_row"] for r in ctx.rows if looks_like_email(val(r, "claim.handler"))]
        return self.result(bad, f"Email address in handler field on {rows_ref(bad)}", "Handler names well-formed",
                           "Handler field contains email address", "Record the handler's name; the email is kept in lineage.")


@register
class NegativeReserves(Rule):
    id, name, severity, dimension, applies_to = "NEG_RESERVE", "No negative reserves", "warning", "accuracy", C

    def check(self, ctx):
        fields = [f for f in ("claim.outstanding", "claim.reserve_gross", "claim.paid_to_date") if f in ctx.mapped_fields]
        if not fields:
            return self.skipped("no reserve fields mapped")
        bad = [r["_row"] for r in ctx.rows for f in fields if (v := num(r, f)) is not None and v < 0]
        return self.result(bad, f"Negative amount on {rows_ref(bad)}", "No negative reserves", "Negative reserve or paid amount",
                           "Confirm whether this is a recovery (should be reported separately).")
