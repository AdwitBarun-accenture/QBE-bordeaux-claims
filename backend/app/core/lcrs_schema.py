"""LCRS canonical data model used by the mockup (48 fields in 7 groups) plus
metadata the agents need: data type, which file type makes it mandatory, and
header synonyms for deterministic (non-AI) mapping.

NOTE: the mockup labels this 'LCRS v3.2'. The real Lloyd's Coverholder Reporting
Standards are currently v5.x with different field names. Keep this registry as
the single source of truth and align it with the version your market uses;
every agent reads from here.
"""
from dataclasses import dataclass, field
from enum import Enum


class DType(str, Enum):
    STRING = "string"
    DATE = "date"
    DECIMAL = "decimal"
    PERCENT = "percent"
    CURRENCY = "currency"   # ISO 4217 code
    COUNTRY = "country"     # ISO 3166 alpha-2
    CODE = "code"           # value from a code list (COB, status...)
    TEXT = "text"           # long free text


class FileType(str, Enum):
    PREMIUM = "premium"
    CLAIMS = "claims"


@dataclass(frozen=True)
class LcrsField:
    name: str
    dtype: DType
    description: str
    mandatory_for: tuple[FileType, ...] = ()
    synonyms: tuple[str, ...] = ()
    derived: bool = False   # produced by enrichment, never mapped from source

    @property
    def group(self) -> str:
        return self.name.split(".")[0]


P, C = FileType.PREMIUM, FileType.CLAIMS

FIELDS: list[LcrsField] = [
    # ---- policy ----
    LcrsField("policy.unique_market_reference", DType.STRING, "Unique Market Reference (UMR)", (P,), ("umr", "unique market reference", "market ref", "agreement number", "binder umr")),
    LcrsField("policy.reference", DType.STRING, "Coverholder policy / certificate reference", (C,), ("our ref", "policy ref", "policy no", "policy number", "certificate ref", "cert no", "policy reference")),
    LcrsField("policy.inception_date", DType.DATE, "Risk inception date", (P,), ("inception", "inception date", "on risk date", "start date", "effective date", "period from")),
    LcrsField("policy.expiry_date", DType.DATE, "Risk expiry date", (P,), ("expiry", "expiry date", "off risk date", "end date", "period to", "expiration date")),
    LcrsField("policy.endorsement_date", DType.DATE, "Endorsement effective date", (), ("endorsement date", "endt date", "mta date")),
    LcrsField("policy.cancellation_date", DType.DATE, "Cancellation date", (), ("cancellation date", "cancel date", "canx date")),
    LcrsField("policy.status", DType.CODE, "Policy transaction status", (), ("policy status", "transaction type", "trans type")),
    # ---- insured ----
    LcrsField("insured.name", DType.STRING, "Insured name", (P, C), ("insured", "insured name", "assured", "policyholder", "client name", "name of insured")),
    LcrsField("insured.reference", DType.STRING, "Insured reference", (), ("insured ref", "client ref", "insured id")),
    LcrsField("insured.address", DType.STRING, "Insured address", (), ("insured address", "client address")),
    LcrsField("insured.country", DType.COUNTRY, "Insured country", (), ("insured country", "domicile")),
    # ---- risk ----
    LcrsField("risk.class_of_business", DType.CODE, "Class of business code", (P,), ("class", "class of business", "cob", "line of business", "lob", "risk class")),
    LcrsField("risk.tmc_code", DType.CODE, "Risk / TMC code", (), ("risk code", "tmc code", "lloyds risk code"), derived=True),
    LcrsField("risk.description", DType.TEXT, "Risk description", (), ("risk description", "description of risk", "occupation", "coverage description")),
    LcrsField("risk.address", DType.STRING, "Risk location address", (), ("location", "risk address", "risk location", "address", "situation")),
    LcrsField("risk.country", DType.COUNTRY, "Risk country", (), ("cntry", "country", "risk country", "location country")),
    LcrsField("risk.sum_insured", DType.DECIMAL, "Sum insured (100%)", (), ("sum ins", "sum insured", "si", "tsi", "total sum insured", "limit")),
    LcrsField("risk.eml_percent", DType.PERCENT, "Estimated maximum loss %", (), ("eml", "eml %", "pml", "estimated maximum loss")),
    LcrsField("risk.cresta_zone", DType.CODE, "CRESTA zone", (), ("cresta", "cresta zone"), derived=True),
    LcrsField("risk.postcode", DType.STRING, "Risk postcode / zip", (), ("postcode", "post code", "zip", "zip code")),
    # ---- premium ----
    LcrsField("premium.gross_original", DType.DECIMAL, "Gross premium (original currency)", (P,), ("gross prem", "gross premium", "gwp", "gross written premium", "premium")),
    LcrsField("premium.net_written", DType.DECIMAL, "Net written premium (our share)", (), ("net prem written", "net premium", "nwp", "net written", "net prem")),
    LcrsField("premium.currency", DType.CURRENCY, "Premium currency", (P,), ("ccy", "currency", "orig ccy", "settlement currency", "premium currency")),
    LcrsField("premium.exchange_rate", DType.DECIMAL, "Rate to GBP", (), ("roe", "rate of exchange", "fx rate", "exchange rate"), derived=True),
    LcrsField("premium.gbp_equivalent", DType.DECIMAL, "Gross premium in GBP", (), ("gbp equivalent", "gross gbp"), derived=True),
    LcrsField("premium.signed_line", DType.PERCENT, "Signed line %", (), ("our line %", "our line", "signed line", "line %", "share %", "written line")),
    LcrsField("premium.subscription_share", DType.PERCENT, "Subscription share %", (), ("subscription share", "syndicate share"), derived=True),
    LcrsField("premium.expense_ratio", DType.PERCENT, "Expense ratio %", (), ("exp ratio", "expense ratio", "expenses %")),
    LcrsField("premium.brokerage", DType.PERCENT, "Brokerage / commission %", (), ("comm %", "commission", "commission %", "brokerage", "brokerage %", "comm")),
    # ---- claim ----
    LcrsField("claim.reference", DType.STRING, "Claim reference", (C,), ("claim ref", "claim reference", "claim no", "claim number", "clm ref")),
    LcrsField("claim.date_of_loss", DType.DATE, "Date of loss", (C,), ("loss date", "date of loss", "dol", "incident date")),
    LcrsField("claim.date_reported", DType.DATE, "Date notified", (C,), ("notified", "date notified", "date reported", "notification date", "reported date")),
    LcrsField("claim.description", DType.TEXT, "Loss description", (), ("cause of loss", "loss description", "claim description", "circumstances")),
    LcrsField("claim.loss_type", DType.CODE, "Type of loss", (), ("type of loss", "loss type", "peril")),
    LcrsField("claim.reserve_gross", DType.DECIMAL, "Gross reserve", (), ("gross reserve", "reserve", "initial reserve")),
    LcrsField("claim.paid_to_date", DType.DECIMAL, "Paid to date", (C,), ("paid", "paid to date", "total paid", "indemnity paid")),
    LcrsField("claim.outstanding", DType.DECIMAL, "Outstanding reserve", (C,), ("o/s reserve", "os reserve", "outstanding", "outstanding reserve", "o s reserve")),
    LcrsField("claim.total_incurred", DType.DECIMAL, "Total incurred", (C,), ("total incurred", "incurred", "total incurred gross")),
    LcrsField("claim.currency", DType.CURRENCY, "Claim currency", (C,), ("claim ccy", "claim currency", "loss currency", "ccy", "currency")),
    LcrsField("claim.status", DType.CODE, "Claim status", (C,), ("status", "claim status")),
    LcrsField("claim.handler", DType.STRING, "Claim handler", (), ("handler", "claim handler", "adjuster", "tpa handler")),
    LcrsField("claim.coverage_type", DType.CODE, "Coverage section", (), ("coverage type", "section", "coverage")),
    # ---- broker ----
    LcrsField("broker.name", DType.STRING, "Broker name", (), ("broker", "broker name", "producing broker", "placing broker")),
    LcrsField("broker.reference", DType.STRING, "Broker reference", (), ("broker ref", "broker reference")),
    LcrsField("broker.pseudonym", DType.CODE, "Broker pseudonym / code", (), ("bkr code", "broker code", "broker pseudonym", "broker id")),
    # ---- coverholder ----
    LcrsField("coverholder.name", DType.STRING, "Coverholder name", (), ("coverholder", "coverholder name", "mga")),
    LcrsField("coverholder.reference", DType.STRING, "Coverholder reference / PIN", (), ("coverholder ref", "coverholder pin", "ch pin")),
    LcrsField("coverholder.binding_authority", DType.STRING, "Binding authority / DA limit", (), ("binding authority", "da limit", "delegated authority")),
]

# Extension fields produced by cleansing (outside LCRS; kept for audit/DQ).
DERIVED_EXTENSIONS = [
    LcrsField("derived.net_written_calculated", DType.DECIMAL, "gross x signed line %", derived=True),
    LcrsField("derived.brokerage_amount", DType.DECIMAL, "gross x brokerage %", derived=True),
    LcrsField("derived.expense_amount", DType.DECIMAL, "gross x expense ratio %", derived=True),
    LcrsField("derived.claim_gbp_incurred", DType.DECIMAL, "total incurred in GBP", derived=True),
]

FIELD_INDEX: dict[str, LcrsField] = {f.name: f for f in FIELDS + DERIVED_EXTENSIONS}
LCRS_FIELD_NAMES: list[str] = [f.name for f in FIELDS]
MAPPABLE_FIELDS: list[str] = [f.name for f in FIELDS if not f.derived]


def mandatory_fields(file_type: str) -> list[str]:
    ft = FileType(file_type)
    return [f.name for f in FIELDS if ft in f.mandatory_for]


def dtype_of(name: str) -> DType | None:
    f = FIELD_INDEX.get(name)
    return f.dtype if f else None


def fields_for_prompt(file_type: str) -> list[dict]:
    """Compact field catalogue sent to the Mapping Agent's LLM prompt."""
    groups = {"premium": {"policy", "insured", "risk", "premium", "broker", "coverholder"},
              "claims": {"policy", "insured", "risk", "claim", "broker", "coverholder"}}[file_type]
    return [{"field": f.name, "type": f.dtype.value, "desc": f.description}
            for f in FIELDS if not f.derived and f.group in groups]
