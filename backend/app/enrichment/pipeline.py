"""Ordered list of cleansing + enrichment steps. Reorder/add steps here."""
from app.enrichment.base import StepContext
from app.enrichment.enrich import CrestaZone, ExpenseAllocation, SubscriptionShare, TmcCode
from app.enrichment.fx import FxNormalisation
from app.enrichment.normalise import (BrokerNormalisation, ClaimStatusNormalisation, CobNormalisation, CountryNormalisation,
                                      CoverholderFill, CurrencyNormalisation, DateNormalisation, HandlerNormalisation,
                                      NumberNormalisation, TrimWhitespace)


def default_steps():
    return [
        TrimWhitespace(), NumberNormalisation(), DateNormalisation(), CurrencyNormalisation(), CountryNormalisation(),
        CobNormalisation(), BrokerNormalisation(), ClaimStatusNormalisation(), HandlerNormalisation(), CoverholderFill(),
        FxNormalisation(), TmcCode(), SubscriptionShare(), CrestaZone(), ExpenseAllocation(),
    ]


def run_steps(rows: list[dict], ctx: StepContext, steps=None):
    steps = steps or default_steps()
    lineage, per_step = [], {s.name: 0 for s in steps if ctx.file_type in s.applies_to}
    for row in rows:
        for s in steps:
            if ctx.file_type not in s.applies_to:
                continue
            changes = s.apply(row, ctx)
            per_step[s.name] += len(changes)
            lineage += changes
    summary = [{"step": s.name, "description": s.description, "changes": per_step[s.name]}
               for s in steps if ctx.file_type in s.applies_to]
    return rows, [c.to_dict() for c in lineage], summary
