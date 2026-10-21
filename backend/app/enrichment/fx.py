"""FX normalisation. RateProvider is pluggable: StaticRateProvider reads
reference_data/fx_rates.json; implement get_rate() against your rate source
(e.g. Lloyd's settlement rates, BoE) for production, ideally by rate date."""
from app.enrichment.base import Step
from app.utils.numbers import fmt_num, parse_decimal
from app.utils.reference import load_ref


class RateProvider:
    def get_rate(self, ccy: str, on_date: str | None = None) -> float | None:
        raise NotImplementedError


class StaticRateProvider(RateProvider):
    def get_rate(self, ccy, on_date=None):
        return load_ref("fx_rates")["rates"].get((ccy or "").upper())


class FxNormalisation(Step):
    name, description = "FX normalisation", "Original currency -> GBP at configured rates"

    def __init__(self, provider: RateProvider | None = None):
        self.provider = provider or StaticRateProvider()

    def apply(self, row, ctx):
        ch = []
        if ctx.file_type == "premium":
            ccy = row.get("premium.currency") or "GBP"
            rate = self.provider.get_rate(ccy, row.get("policy.inception_date"))
            if rate is None:
                row.setdefault("_dq_flags", []).append(f"NO_FX_RATE:{ccy}")
                return []
            ch += self.set(row, "premium.exchange_rate", fmt_num(rate, 6), self.name)
            g = parse_decimal(row.get("premium.gross_original"))
            if g is not None:
                ch += self.set(row, "premium.gbp_equivalent", fmt_num(float(g) * rate, 2), self.name)
        else:
            ccy = row.get("claim.currency") or "GBP"
            rate = self.provider.get_rate(ccy, row.get("claim.date_of_loss"))
            t = parse_decimal(row.get("claim.total_incurred"))
            if rate is not None and t is not None:
                ch += self.set(row, "derived.claim_gbp_incurred", fmt_num(float(t) * rate, 2), self.name)
        return ch
