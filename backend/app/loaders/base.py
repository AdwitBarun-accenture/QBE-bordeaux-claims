from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LoadResult:
    load_id: str
    target: str
    rows_written: int
    rows_flagged: int
    control_total_gbp: float
    errors: list[str] = field(default_factory=list)


class Warehouse(ABC):
    """Target data warehouse for the final canonical LCRS dataset."""

    @abstractmethod
    def load(self, records: list[dict], meta: dict) -> LoadResult: ...

    @abstractmethod
    def prior_umrs(self, coverholder: str, exclude_file_id: str = "") -> set[str]: ...

    @abstractmethod
    def written_gbp_ytd(self, coverholder: str, year: int, exclude_file_id: str = "") -> float: ...

    @abstractmethod
    def count_for_load(self, load_id: str) -> int: ...

    # analytics used by the Insights page
    def portfolio(self) -> dict:
        return {}
