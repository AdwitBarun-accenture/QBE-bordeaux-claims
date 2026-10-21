from app.utils.dates import parse_date
from app.utils.json_utils import extract_json
from app.utils.numbers import parse_decimal


def test_dates():
    assert parse_date("01/04/2026").iso == "2026-04-01"
    p = parse_date("04/15/2026")
    assert p.iso == "2026-04-15" and p.fmt == "mdy"
    assert parse_date("2026").fmt == "year_only"
    assert parse_date("04/10/2026").ambiguous
    assert parse_date("10 Jan 26").iso == "2026-01-10"
    assert parse_date("46113").fmt == "excel_serial"


def test_numbers():
    assert parse_decimal("2.5m") == 2_500_000
    assert parse_decimal("(1,200)") == -1200
    assert parse_decimal("£45,200") == 45200
    assert parse_decimal("+45k") == 45000
    assert parse_decimal("abc") is None


def test_extract_json():
    assert extract_json('Sure!\n```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert extract_json('result: {"x": [1,2]} done') == {"x": [1, 2]}


def test_date_rule_trusts_profile_unless_mixed():
    from app.rules.base import RuleContext
    from app.rules.common_rules import DateFormatConsistency
    base = dict(file_type="premium", settings={}, mapped_fields={"policy.inception_date"}, date_order="dmy", date_order_source="profile")
    clean = [{"_row": 1, "policy.inception_date": "01/04/2026"}, {"_row": 2, "policy.inception_date": "20/04/2026"}]
    assert DateFormatConsistency().check(RuleContext(rows=clean, **base)).passed
    mixed = clean + [{"_row": 3, "policy.inception_date": "04/15/2026"}]
    res = DateFormatConsistency().check(RuleContext(rows=mixed, **base))
    assert set(res.failing_rows) == {1, 3}      # the US row + the now-uncertain ambiguous row
