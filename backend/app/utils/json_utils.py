"""Safe JSON handling (Decimals, dates) and robust extraction of JSON from LLM text."""
import json
import re
from datetime import date, datetime
from decimal import Decimal


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(f"not JSON serialisable: {type(o)}")


def dumps(obj, **kw) -> str:
    return json.dumps(obj, default=_default, **kw)


def to_jsonable(obj):
    return json.loads(dumps(obj))


_FENCE = re.compile(r"```(?:json)?", re.I)


def extract_json(text: str):
    """LLMs sometimes wrap JSON in fences or add a sentence. Find the first
    balanced JSON object/array and parse it. Raises ValueError if none."""
    if not text:
        raise ValueError("empty LLM response")
    cleaned = _FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    candidates = sorted(
        [(cleaned.find(c), c) for c in "[{" if cleaned.find(c) != -1]
    )
    for start, open_ch in candidates:
        close_ch = "]" if open_ch == "[" else "}"
        depth, in_str, esc = 0, False, False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start: i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError("no JSON found in LLM response")
