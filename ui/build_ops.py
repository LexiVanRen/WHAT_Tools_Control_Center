# ui/build_ops.py
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

import requests

INNO_COMPILER = r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
SERVER = "https://rndserver-stg.abcparts.be"
UPDATE_MANIFEST_BASE = f"{SERVER}/api/update_manifest"
ADD_APP_TO_MANIFEST_URL = f"{SERVER}/api/add_app_to_manifest"


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    message: str
    latest_installer: str = ""


def _run(cmd: list[str], cwd: str) -> None:
    startupinfo = None
    creationflags = 0

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def _find_spec(repo: Path) -> Optional[Path]:
    # Match legacy script (WHAT.spec) first, then common main.spec, else any *.spec
    for name in ("WHAT.spec", "main.spec"):
        p = repo / name
        if p.is_file():
            return p
    specs = sorted(repo.glob("*.spec"))
    return specs[0] if specs else None


def _pyinstaller_cmd(repo: Path, spec: Path) -> list[str]:
    """
    Matches the two build scripts:
      - If repo has Python27 + PyInstaller-3.2.1 runner -> use that (legacy)
      - Else if repo has venv with pyton --> use this
      - Fallback
    """
    py27 = repo / "Python27" / "python.exe"
    pi_runner = repo / "Python27" / "PyInstaller-3.2.1" / "pyinstaller.py"
    if py27.is_file() and pi_runner.is_file():
        return [str(py27), str(pi_runner), "--clean", str(spec.name)]


    venv_python = repo / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return [str(venv_python), "-m", "PyInstaller", "--clean", "-y", str(spec.name)]

    # fallback
    return [sys.executable, "-m", "PyInstaller", "--clean", "-y", str(spec.name)]


_NAME_RE = re.compile(r'^\s*#define\s+MyAppName\s+"(.+)"\s*$', re.IGNORECASE)
_VER_RE = re.compile(r'^\s*#define\s+MyAppVersion\s+"(.+)"\s*$', re.IGNORECASE)


def read_inno_app_info(iss_path: Path) -> tuple[str, str]:
    app_name = ""
    app_version = ""
    if not iss_path.is_file():
        return "", ""

    for line in iss_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = _NAME_RE.match(line.strip())
        if m:
            app_name = m.group(1).strip()
        m = _VER_RE.match(line.strip())
        if m:
            app_version = m.group(1).strip()

    return app_name, app_version


def newest_exe_in(folder: Path) -> Optional[Path]:
    if not folder.is_dir():
        return None
    exes = list(folder.glob("*.exe"))
    if not exes:
        return None
    return max(exes, key=lambda p: p.stat().st_mtime)


def build_repo(repo_path: str, iss_path: str) -> BuildResult:
    repo = Path(repo_path)
    iss = Path(iss_path)

    if not repo.is_dir():
        return BuildResult(False, f"Repo not found: {repo}")

    spec = _find_spec(repo)
    if not spec:
        return BuildResult(False, f"No .spec found in: {repo}")

    # (Ethernet script removes dist/Ethernet; legacy removes build/ and dist/)
    # We keep it conservative: if "build" or "dist" exist, remove them (same outcome).
    for d in ("build", "dist"):
        p = repo / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    try:
        # 1) PyInstaller
        _run(_pyinstaller_cmd(repo, spec), cwd=str(repo))

        # 2) Inno
        if not os.path.exists(INNO_COMPILER):
            return BuildResult(False, f"Inno compiler not found: {INNO_COMPILER}")

        if not iss.is_file():
            return BuildResult(False, f".iss not found: {iss}")

        _run([INNO_COMPILER, str(iss.name)], cwd=str(repo))

        # 3) Find latest installer
        latest = newest_exe_in(repo / "Output")
        if not latest:
            return BuildResult(False, "Build ok, but no installer exe found in Output/")

        return BuildResult(True, "Build OK", latest_installer=str(latest))
    except subprocess.CalledProcessError as e:
        return BuildResult(False, f"Build failed: {e}")


def copy_installer(installer_exe: str, installers_dir: str) -> BuildResult:
    src = Path(installer_exe)
    dst_dir = Path(installers_dir)
    if not src.is_file():
        return BuildResult(False, f"Installer not found: {src}")
    dst_dir.mkdir(parents=True, exist_ok=True)

    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return BuildResult(True, f"Copied to {dst}", latest_installer=str(dst))


def update_manifest_from_iss(iss_path: str) -> BuildResult:
    iss = Path(iss_path)
    app_name, app_version = read_inno_app_info(iss)
    if not app_name or not app_version:
        return BuildResult(False, f"Could not read MyAppName/MyAppVersion from {iss}")

    url = f"{UPDATE_MANIFEST_BASE}/{app_name}_{app_version}_y"
    try:
        resp = requests.patch(url, json={}, timeout=10)
        if resp.status_code == 200:
            return BuildResult(True, f"Manifest updated: {app_name} -> {app_version}")
        return BuildResult(False, f"Manifest update failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        return BuildResult(False, f"Manifest update error: {e}")


def add_app_to_manifest(payload: dict) -> BuildResult:
    try:
        resp = requests.post(ADD_APP_TO_MANIFEST_URL, json=payload, timeout=12)
        if resp.status_code in (200, 201):
            return BuildResult(True, "New app added to manifest.")

        err_text = resp.text
        try:
            data = resp.json()
            if isinstance(data, dict):
                if data.get("message"):
                    err_text = str(data.get("message"))
                elif data.get("error"):
                    err_text = str(data.get("error"))
        except Exception:
            pass
        return BuildResult(False, f"Add app failed ({resp.status_code}): {err_text}")
    except Exception as e:
        return BuildResult(False, f"Add app request error: {e}")
