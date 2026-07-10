import hashlib
import json
import re
from collections.abc import Mapping, Sequence


def stable_hash(value: str | Mapping[str, object] | Sequence[object]) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    normalized = re.sub(r"\s+", " ", value).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
