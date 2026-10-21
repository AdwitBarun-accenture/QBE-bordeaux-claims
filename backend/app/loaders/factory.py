from functools import lru_cache
from urllib.parse import quote_plus

from app.core.config import get_settings
from app.loaders.base import Warehouse


@lru_cache
def get_warehouse() -> Warehouse:
    s = get_settings()
    if s.dwh_loader == "csv":
        from app.loaders.warehouse_csv import CsvWarehouse
        return CsvWarehouse()
    from app.loaders.warehouse_sql import SqlWarehouse
    if s.dwh_loader == "snowflake":
        url = (f"snowflake://{quote_plus(s.snowflake_user)}:{quote_plus(s.snowflake_password)}@{s.snowflake_account}/"
               f"{s.snowflake_database}/{s.snowflake_schema}?warehouse={s.snowflake_warehouse}")
        return SqlWarehouse(url)
    return SqlWarehouse(s.dwh_database_url or s.database_url)
