"""Rule framework. A rule is a small class with an id, severity, the quality
dimension it affects, the file types it applies to and a check() method that
returns the failing row numbers. Add a rule = add a class with @register."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

SEVERITY_TO_EXCEPTION = {"error": "high", "warning": "medium", "info": "low"}


@dataclass
class RuleContext:
    rows: list[dict]                 # canonical rows (raw string values) with '_row'
    file_type: str
    settings: dict                   # runtime pipeline settings
    mapped_fields: set[str]
    date_order: str = "dmy"
    date_order_source: str = "inferred"   # 'profile' when set on the coverholder
    coverholder: dict = field(default_factory=dict)   # {name, da_limit_gbp}
    prior_umrs: set[str] = field(default_factory=set) # UMRs loaded in earlier submissions
    prior_written_gbp: float = 0.0                    # YTD GBP gross already loaded


@dataclass
class RuleResult:
    rule_id: str
    rule: str
    severity: str                    # error | warning | info
    dimension: str                   # completeness | accuracy | consistency
    passed: bool
    failing_rows: list[int] = field(default_factory=list)
    detail: str = ""
    exception_title: str = ""
    suggestion: str = ""
    skipped: bool = False

    @property
    def count(self) -> int:
        return len(self.failing_rows)

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "rule": self.rule, "severity": self.severity, "dimension": self.dimension,
                "passed": self.passed, "count": self.count, "rows": self.failing_rows[:200], "detail": self.detail,
                "skipped": self.skipped}


class Rule(ABC):
    id: str = ""
    name: str = ""
    severity: str = "warning"
    dimension: str = "accuracy"
    applies_to: tuple[str, ...] = ("premium", "claims")
    requires: tuple[str, ...] = ()   # canonical fields that must be mapped for the rule to run

    def result(self, failing: list[int], detail_fail: str, detail_pass: str, title: str = "", suggestion: str = "") -> RuleResult:
        failing = sorted(set(failing))
        return RuleResult(self.id, self.name, self.severity, self.dimension, not failing, failing,
                          detail_fail if failing else detail_pass, title or self.name, suggestion)

    def skipped(self, why: str) -> RuleResult:
        return RuleResult(self.id, self.name, "info", self.dimension, True, [], f"Not run: {why}", skipped=True)

    @abstractmethod
    def check(self, ctx: RuleContext) -> RuleResult: ...


REGISTRY: list[type[Rule]] = []


def register(cls: type[Rule]) -> type[Rule]:
    REGISTRY.append(cls)
    return cls


def rows_ref(rows: list[int], n: int = 6) -> str:
    s = ", ".join(str(r) for r in rows[:n])
    return f"row{'s' if len(rows) > 1 else ''} {s}{'…' if len(rows) > n else ''}"
