import json
import urllib.request
from pathlib import Path
from typing import Any

from ui.models import ManifestData, parse_manifest


MANIFEST_SAVE_PATH = Path.home() / "Documents" / "ABC_WHAT_Tools" / "manifest.json"


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
    MANIFEST_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_SAVE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return parse_manifest(payload, source_url=url)
