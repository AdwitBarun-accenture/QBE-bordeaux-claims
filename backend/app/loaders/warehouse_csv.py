"""Dev-only loader: writes the final dataset as CSV into staged storage."""
import csv
import io
import uuid

from app.loaders.base import LoadResult, Warehouse
from app.storage.factory import get_store
from app.utils.numbers import parse_float


class CsvWarehouse(Warehouse):
    def load(self, records, meta):
        load_id = uuid.uuid4().hex
        keys = sorted({k for r in records for k in r if not k.startswith("_")})
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["source_row", "dq_flags"] + keys, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({**r, "source_row": r.get("_row"), "dq_flags": ";".join(r.get("_dq_flags", []))})
        get_store().put_staged(f"dwh/{meta['coverholder']}/{load_id}.csv", buf.getvalue().encode())
        total = sum(parse_float(r.get("premium.gbp_equivalent")) or 0 for r in records)
        return LoadResult(load_id, "csv", len(records), sum(bool(r.get("_dq_flags")) for r in records), round(total, 2))

    def count_for_load(self, load_id):
        return -1  # not verifiable for CSV

    def prior_umrs(self, coverholder, exclude_file_id=""):
        return set()

    def written_gbp_ytd(self, coverholder, year, exclude_file_id=""):
        return 0.0
