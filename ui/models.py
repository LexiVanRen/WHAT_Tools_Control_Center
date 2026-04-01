from dataclasses import dataclass
from typing import Any


MANIFEST_URL = "https://rndserver-stg.abcparts.be/abc_applauncher/manifest.json"
GITHUB_ROOT = r"C:\Users\ABC-RnD\Documents\GitHub"
WHAT_REPO_FOLDER = "Applauncher"
INNO_ISS_RELATIVE = "inno_setup_script_for_making_installer.iss"
GITHUB_REPO_OVERRIDES = {
    "CAN": r"C:\Users\ABC-RnD\PycharmProjects\CAN",
}
# Where installers are dropped (your network drive)
INSTALLERS_DIR = r"Z:\R&D\WHAT_installers"


@dataclass(frozen=True)
class AppEntry:
    name: str
    version: str
    description: str


@dataclass(frozen=True)
class ManifestData:
    source_url: str
    launcher_version: str
    launcher_info: str
    apps: list[AppEntry]


def parse_manifest(payload: dict[str, Any], *, source_url: str) -> ManifestData:
    """
    Manifest rules:
    - Top-level: "version" + "Info" represents the WHAT application.
    - "Apps": dict of real apps with "latest_version" + "description".
    """
    launcher_info = str(payload.get("Info", "") or "").strip()
    launcher_version = str(payload.get("version", "") or "").strip()

    apps: list[AppEntry] = []

    # Add WHAT from top-level manifest fields
    apps.append(
        AppEntry(
            name="WHAT",
            version=launcher_version if launcher_version else "",
            description=launcher_info,
        )
    )

    apps_block = payload.get("Apps", {}) or {}
    for name in sorted(apps_block.keys(), key=lambda s: s.lower()):
        a = apps_block.get(name, {}) or {}
        apps.append(
            AppEntry(
                name=str(name),
                version=str(a.get("latest_version", "") or "").strip(),
                description=str(a.get("description", "") or "").strip(),
            )
        )

    return ManifestData(
        source_url=source_url,
        launcher_version=launcher_version,
        launcher_info=launcher_info,
        apps=apps,
    )
