import json
import urllib.request
from typing import Any

from ui.models import ManifestData, parse_manifest


def fetch_manifest(url: str, timeout_s: float = 8.0) -> ManifestData:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ABC-BuildLauncher/1.0",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    payload: dict[str, Any] = json.loads(raw)
    return parse_manifest(payload, source_url=url)
