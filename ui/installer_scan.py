from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ui.windows_version import get_file_product_version


@dataclass(frozen=True)
class InstallerInfo:
    exe_path: str
    last_built: datetime
    product_version: str


def find_installer_for_app(installers_dir: str, app_name: str) -> Optional[InstallerInfo]:
    """
    Looks in installers_dir for the installer matching the naming convention:

      <AppName>_installer.exe

    Your Explorer hides extensions, so we accept:
      - exact: Serial_installer.exe
      - or any: Serial_installer* (and then we pick the newest .exe)

    Returns newest match if multiple exist.
    """
    base = app_name.strip()
    if not base:
        return None

    root = Path(installers_dir)
    if not root.exists():
        return None

    # Prefer exact match first
    exact = root / f"{base}_installer.exe"
    candidates: list[Path] = []

    if exact.exists():
        candidates.append(exact)

    # Also search broader patterns (in case naming differs or extension omitted somewhere)
    # Use glob for exe + non-exe (some environments keep no extension, but Windows apps are usually .exe)
    candidates.extend(root.glob(f"{base}_installer*.exe"))
    candidates.extend(root.glob(f"{base}_installer*"))

    # Filter to files only
    candidates = [p for p in candidates if p.is_file()]

    if not candidates:
        return None

    # pick the most recently modified
    newest = max(candidates, key=lambda p: p.stat().st_mtime)

    mtime = datetime.fromtimestamp(newest.stat().st_mtime)
    prod_ver = ""
    try:
        prod_ver = get_file_product_version(str(newest))
    except Exception:
        prod_ver = ""

    return InstallerInfo(
        exe_path=str(newest),
        last_built=mtime,
        product_version=prod_ver.strip(),
    )
