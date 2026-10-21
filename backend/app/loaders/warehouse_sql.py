"""SQL warehouse loader. One implementation for every SQLAlchemy dialect:
  sqlite:///./dwh.db                                  (local)
  postgresql+psycopg://...                            (Azure Database for PostgreSQL)
  mssql+pyodbc://...?driver=ODBC+Driver+18+for+SQL+Server  (Azure SQL / Fabric warehouse)
  snowflake://user:pw@account/db/schema?warehouse=WH  (Snowflake, needs snowflake-sqlalchemy)

The load is a single transaction: either every record of the file lands, or none
(100% data preservation; flagged rows are loaded with dq_status='flagged')."""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String, Table, Text, case, create_engine, func, select)

from app.loaders.base import LoadResult, Warehouse
from app.utils.dates import parse_date
from app.utils.numbers import parse_float

md = MetaData()
lcrs_records = Table(
    "dwh_lcrs_records", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("load_id", String(32), index=True), Column("file_id", String(32), index=True), Column("run_id", String(32)),
    Column("coverholder", String(200), index=True), Column("record_type", String(16)), Column("source_row", Integer),
    Column("umr", String(64), index=True), Column("policy_ref", String(100)), Column("claim_ref", String(100)),
    Column("insured", String(300)), Column("cob", String(16)), Column("tmc_code", String(16)),
    Column("currency", String(3)), Column("gross_original", Float), Column("gross_gbp", Float),
    Column("net_written", Float), Column("sum_insured", Float), Column("inception_date", String(10)),
    Column("expiry_date", String(10)), Column("date_of_loss", String(10)), Column("paid", Float),
    Column("outstanding", Float), Column("total_incurred", Float), Column("incurred_gbp", Float),
    Column("claim_status", String(32)), Column("dq_status", String(16)), Column("dq_flags", Text),
    Column("record_json", Text), Column("schema_version", String(16)),
    Column("loaded_at", DateTime(timezone=True)),
)


def _iso(v):
    p = parse_date(v)
    return p.iso or None


class SqlWarehouse(Warehouse):
    def __init__(self, url: str):
        self.url = url
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
        self.engine = create_engine(url, **kw)
        md.create_all(self.engine)

    def load(self, records, meta):
        load_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        rows, flagged, total = [], 0, 0.0
        for r in records:
            flags = r.get("_dq_flags", [])
            flagged += bool(flags)
            gbp = parse_float(r.get("premium.gbp_equivalent")) or 0.0
            total += gbp
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            rows.append({
                "load_id": load_id, "file_id": meta["file_id"], "run_id": meta["run_id"], "coverholder": meta["coverholder"],
                "record_type": meta["file_type"], "source_row": r.get("_row"),
                "umr": r.get("policy.unique_market_reference") or None, "policy_ref": r.get("policy.reference") or None,
                "claim_ref": r.get("claim.reference") or None, "insured": r.get("insured.name") or None,
                "cob": r.get("risk.class_of_business") or None, "tmc_code": r.get("risk.tmc_code") or None,
                "currency": r.get("premium.currency") or r.get("claim.currency") or None,
                "gross_original": parse_float(r.get("premium.gross_original")), "gross_gbp": gbp or None,
                "net_written": parse_float(r.get("premium.net_written")), "sum_insured": parse_float(r.get("risk.sum_insured")),
                "inception_date": _iso(r.get("policy.inception_date")), "expiry_date": _iso(r.get("policy.expiry_date")),
                "date_of_loss": _iso(r.get("claim.date_of_loss")), "paid": parse_float(r.get("claim.paid_to_date")),
                "outstanding": parse_float(r.get("claim.outstanding")), "total_incurred": parse_float(r.get("claim.total_incurred")),
                "incurred_gbp": parse_float(r.get("derived.claim_gbp_incurred")), "claim_status": r.get("claim.status") or None,
                "dq_status": "flagged" if flags else "clean", "dq_flags": json.dumps(flags),
                "record_json": json.dumps(clean, default=str), "schema_version": meta.get("schema_version"), "loaded_at": now,
            })
        with self.engine.begin() as conn:   # atomic
            if rows:
                conn.execute(lcrs_records.insert(), rows)
        return LoadResult(load_id, self.url.split("://")[0], len(rows), flagged, round(total, 2))

    def count_for_load(self, load_id):
        with self.engine.connect() as c:
            return c.execute(select(func.count()).select_from(lcrs_records).where(lcrs_records.c.load_id == load_id)).scalar() or 0

    def prior_umrs(self, coverholder, exclude_file_id=""):
        q = select(lcrs_records.c.umr).where(lcrs_records.c.coverholder == coverholder, lcrs_records.c.umr.is_not(None))
        if exclude_file_id:
            q = q.where(lcrs_records.c.file_id != exclude_file_id)
        with self.engine.connect() as c:
            return {(u or "").upper() for (u,) in c.execute(q)}

    def written_gbp_ytd(self, coverholder, year, exclude_file_id=""):
        q = select(func.coalesce(func.sum(lcrs_records.c.gross_gbp), 0)).where(
            lcrs_records.c.coverholder == coverholder, lcrs_records.c.record_type == "premium",
            lcrs_records.c.inception_date >= f"{year}-01-01", lcrs_records.c.inception_date <= f"{year}-12-31")
        if exclude_file_id:
            q = q.where(lcrs_records.c.file_id != exclude_file_id)
        with self.engine.connect() as c:
            return float(c.execute(q).scalar() or 0)

    # ---------------- analytics for Insights ----------------
    def portfolio(self) -> dict:
        t = lcrs_records.c
        with self.engine.connect() as c:
            prem = t.record_type == "premium"
            kpis = c.execute(select(func.coalesce(func.sum(t.gross_gbp), 0), func.count(func.distinct(t.file_id)),
                                    func.count(), func.sum(case((t.dq_status == "flagged", 1), else_=0)))).one()
            cob = c.execute(select(t.cob, func.sum(t.gross_gbp)).where(prem).group_by(t.cob)
                            .order_by(func.sum(t.gross_gbp).desc())).all()
            monthly = c.execute(select(func.substr(t.inception_date, 1, 7), func.count(func.distinct(t.file_id)))
                                .where(t.inception_date.is_not(None)).group_by(func.substr(t.inception_date, 1, 7))
                                .order_by(func.substr(t.inception_date, 1, 7))).all()
            by_ch = c.execute(select(t.coverholder, t.cob, func.sum(t.gross_gbp)).where(prem).group_by(t.coverholder, t.cob)).all()
            claims = c.execute(select(t.coverholder, func.sum(t.total_incurred), func.sum(t.paid), func.sum(t.outstanding))
                               .where(t.record_type == "claims").group_by(t.coverholder)).all()
        return {
            "gwp_gbp": float(kpis[0] or 0), "files": int(kpis[1] or 0), "records": int(kpis[2] or 0),
            "flagged_records": int(kpis[3] or 0),
            "gwp_by_cob": [{"cob": k or "UNK", "gbp": float(v or 0)} for k, v in cob],
            "files_by_month": [{"month": m, "files": n} for m, n in monthly if m],
            "written_by_coverholder": [{"coverholder": a, "cob": b, "gbp": float(v or 0)} for a, b, v in by_ch],
            "claims_by_coverholder": [{"coverholder": a, "incurred": float(i or 0), "paid": float(p or 0), "outstanding": float(o or 0)}
                                      for a, i, p, o in claims],
        }
