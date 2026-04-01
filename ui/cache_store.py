from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class CachedInstaller:
    product_version: str = ""
    last_built_iso: str = ""        # ISO string (local time not guaranteed)
    exe_path: str = ""


@dataclass
class CachedManifest:
    version: str = ""
    description: str = ""

@dataclass
class CachedGithub:
    repo_path: str = ""
    inno_iss_path: str = ""
    myapp_version: str = ""

@dataclass
class CachedApp:
    name: str
    manifest: CachedManifest
    installer: CachedInstaller
    github: CachedGithub


@dataclass
class AppCache:
    schema: int = 1
    updated_at_utc: str = ""
    source_manifest_url: str = ""
    installers_dir: str = ""
    apps: list[CachedApp] = None  # type: ignore


def default_cache(manifest_url: str, installers_dir: str) -> AppCache:
    return AppCache(
        schema=1,
        updated_at_utc=_utc_now_iso(),
        source_manifest_url=manifest_url,
        installers_dir=installers_dir,
        apps=[],
    )


class CacheStore:
    def __init__(self, cache_path: str):
        self.path = Path(cache_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Optional[AppCache]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return self._from_dict(data)
        except Exception:
            return None

    def save(self, cache: AppCache) -> None:
        cache.updated_at_utc = _utc_now_iso()
        payload = self._to_dict(cache)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _to_dict(self, cache: AppCache) -> dict[str, Any]:
        return asdict(cache)

    def _from_dict(self, d: dict[str, Any]) -> AppCache:
        apps_in = d.get("apps", []) or []
        apps: list[CachedApp] = []
        for a in apps_in:
            manifest = a.get("manifest", {}) or {}
            installer = a.get("installer", {}) or {}
            github = a.get("github", {}) or {}
            apps.append(
                CachedApp(
                    name=str(a.get("name", "")),
                    manifest=CachedManifest(
                        version=str(manifest.get("version", "")),
                        description=str(manifest.get("description", "")),
                    ),
                    installer=CachedInstaller(
                        product_version=str(installer.get("product_version", "")),
                        last_built_iso=str(installer.get("last_built_iso", "")),
                        exe_path=str(installer.get("exe_path", "")),
                    ),
                    github=CachedGithub(
                        repo_path=str(github.get("repo_path", "")),
                        inno_iss_path=str(github.get("inno_iss_path", "")),
                        myapp_version=str(github.get("myapp_version", "")),
                    ),
                )
            )

        return AppCache(
            schema=int(d.get("schema", 1)),
            updated_at_utc=str(d.get("updated_at_utc", "")),
            source_manifest_url=str(d.get("source_manifest_url", "")),
            installers_dir=str(d.get("installers_dir", "")),
            apps=apps,
        )
