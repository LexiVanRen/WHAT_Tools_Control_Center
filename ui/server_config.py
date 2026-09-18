from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PRODUCTION_SERVER = "https://rndserver.abcparts.be"
STAGING_SERVER = "https://rndserver-stg.abcparts.be"
DEFAULT_SERVER_ENVIRONMENT = "staging"

_SERVERS = {
    "production": PRODUCTION_SERVER,
    "staging": STAGING_SERVER,
}

_LOCAL_APP_DATA = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
SETTINGS_PATH = Path(_LOCAL_APP_DATA) / "WHATControlCenter" / "settings.json"


def normalize_server_environment(environment: str) -> str:
    return environment if environment in _SERVERS else DEFAULT_SERVER_ENVIRONMENT


def get_server_base_url(environment: str) -> str:
    return _SERVERS[normalize_server_environment(environment)]


def get_manifest_url(environment: str) -> str:
    return f"{get_server_base_url(environment)}/abc_applauncher/manifest.json"


def load_server_environment() -> str:
    try:
        data: dict[str, Any] = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return normalize_server_environment(str(data.get("server_environment", "")))
    except (OSError, TypeError, ValueError):
        return DEFAULT_SERVER_ENVIRONMENT


def save_server_environment(environment: str) -> None:
    selected = normalize_server_environment(environment)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps({"server_environment": selected}, indent=2) + "\n",
        encoding="utf-8",
    )
