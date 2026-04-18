from __future__ import annotations

import json


def parse_ndjson(response) -> list[dict]:
    lines = [line for line in response.get_data(as_text=True).splitlines() if line.strip()]
    return [json.loads(line) for line in lines]
