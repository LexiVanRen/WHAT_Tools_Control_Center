from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ui.cache_store import CacheStore
from ui.manifest_client import fetch_manifest
from ui.models import github_paths_for_app
from ui.performance_audit import find_codex_executable, run_performance_audit
from ui.server_config import get_manifest_url, load_server_environment


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class AuditTarget:
    name: str
    repo_path: str


@dataclass(frozen=True)
class AuditOutcome:
    name: str
    status: str
    repo_path: str
    report_path: str = ""
    error: str = ""


@dataclass(frozen=True)
class AuditRunResult:
    run_dir: Path
    summary_path: Path
    log_path: Path
    outcomes: tuple[AuditOutcome, ...]
    exit_code: int


def _audit_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "WHATControlCenter" / "performance_audits"


def _new_run_dir() -> Path:
    base = _audit_root() / "runs"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = base / f"run_{stamp}"
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"run_{stamp}_{suffix}"
        suffix += 1
    run_dir.mkdir()
    return run_dir


def _cache_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "WHATControlCenter" / "cache"


def _targets_from_cache() -> list[AuditTarget]:
    cache = CacheStore(str(_cache_path())).load()
    if not cache:
        return []
    targets: list[AuditTarget] = []
    for app in cache.apps or []:
        if not app.name.strip():
            continue
        repo_path = (app.github.repo_path or "").strip()
        if not repo_path:
            repo_path, _ = github_paths_for_app(app.name)
        targets.append(AuditTarget(app.name, repo_path))
    return targets


def _discover_targets() -> tuple[list[AuditTarget], str, str]:
    environment = load_server_environment()
    manifest_url = get_manifest_url(environment)
    try:
        manifest = fetch_manifest(manifest_url, timeout_s=20.0, persist_copy=False)
    except Exception as exc:
        cached_targets = _targets_from_cache()
        if cached_targets:
            warning = (
                f"Could not fetch the {environment} manifest ({exc}); used the locally cached "
                "application list instead. That list may be out of date."
            )
            return cached_targets, f"local cache (server: {environment})", warning
        return [], f"server manifest ({environment})", f"Could not load the tool list: {exc}"

    targets: list[AuditTarget] = []
    seen: set[str] = set()
    for app in manifest.apps:
        name = app.name.strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        repo_path, _ = github_paths_for_app(name)
        targets.append(AuditTarget(name, repo_path))
    return targets, f"server manifest ({environment})", ""


def _normalize_app_name(name: str) -> str:
    return "".join(character.casefold() for character in name if character.isalnum())


def _select_target(targets: list[AuditTarget], requested_name: str) -> tuple[AuditTarget | None, str]:
    requested_name = requested_name.strip()
    exact_matches = [target for target in targets if target.name.casefold() == requested_name.casefold()]
    if len(exact_matches) == 1:
        return exact_matches[0], ""

    normalized_name = _normalize_app_name(requested_name)
    matches = [target for target in targets if _normalize_app_name(target.name) == normalized_name]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        choices = ", ".join(target.name for target in matches)
        return None, f"App name '{requested_name}' is ambiguous; use one of: {choices}."

    available = ", ".join(target.name for target in targets) or "none"
    return None, f"App '{requested_name}' was not found in the tool list. Available tools: {available}."


def _render_summary(
    started_at: datetime,
    finished_at: datetime,
    inventory_source: str,
    warning: str,
    global_error: str,
    outcomes: list[AuditOutcome],
    log_path: Path,
) -> str:
    completed = sum(outcome.status == "COMPLETED" for outcome in outcomes)
    failed = sum(outcome.status == "FAILED" for outcome in outcomes)
    skipped = sum(outcome.status == "SKIPPED" for outcome in outcomes)

    lines = [
        "# Performance audit run",
        "",
        f"- Started: {started_at.astimezone().isoformat(timespec='seconds')}",
        f"- Finished: {finished_at.astimezone().isoformat(timespec='seconds')}",
        f"- Tool list: {inventory_source}",
        f"- Results: {completed} completed, {failed} failed, {skipped} skipped",
        f"- Progress log: `{log_path}`",
    ]
    if warning:
        lines.extend(["", f"> Inventory warning: {warning}"])
    if global_error:
        lines.extend(["", f"**Run setup error:** {global_error}"])

    lines.extend(["", "## Per-tool results", ""])
    if not outcomes:
        lines.append("No tools were audited.")
    else:
        for outcome in outcomes:
            lines.append(f"### {outcome.name} — {outcome.status}")
            lines.append("")
            lines.append(f"- Source: `{outcome.repo_path}`")
            if outcome.report_path:
                lines.append(f"- Report: `{outcome.report_path}`")
            if outcome.error:
                lines.append(f"- Details: {outcome.error.replace(chr(10), ' ')}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _run_audits(
    requested_app: str | None,
    progress: ProgressCallback | None = None,
) -> AuditRunResult:
    """Audit every app, or one selected app, continuing with normal run reporting."""
    run_dir = _new_run_dir()
    summary_path = run_dir / "summary.md"
    log_path = run_dir / "run.log"
    started_at = datetime.now().astimezone()
    outcomes: list[AuditOutcome] = []
    log_lock = threading.Lock()

    def report_progress(message: str) -> None:
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        line = f"[{timestamp}] {message}"
        with log_lock:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(line + "\n")
        if progress:
            progress(message)

    report_progress(
        f"Starting performance audit for {requested_app}."
        if requested_app
        else "Starting full performance audit."
    )
    targets, inventory_source, warning = _discover_targets()
    if warning:
        report_progress(f"Warning: {warning}")

    selection_error = ""
    if requested_app and targets:
        selected_target, selection_error = _select_target(targets, requested_app)
        if selection_error:
            targets = []
        elif selected_target:
            targets = [selected_target]

    app_root = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    ).resolve()
    skill_root = app_root / ".agents" / "skills"
    skill_path = skill_root / "performance-audit" / "SKILL.md"
    global_error = ""
    if not targets:
        global_error = selection_error or warning or "The tool list was empty."
    elif not find_codex_executable():
        global_error = (
            "A directly launchable Codex CLI executable was not found on PATH. Ensure "
            "`codex.exe` is available to the Windows account running this app, then rerun."
        )
    elif not skill_path.is_file():
        global_error = f"Audit skill was not found: {skill_path}"

    if global_error:
        report_progress(f"Run cannot continue: {global_error}")
        outcomes.extend(
            AuditOutcome(target.name, "FAILED", target.repo_path, error=global_error)
            for target in targets
        )
    else:
        for index, target in enumerate(targets, start=1):
            report_progress(f"Tool {index}/{len(targets)}: {target.name}")
            if not Path(target.repo_path).expanduser().is_dir():
                error = f"Source folder does not exist: {Path(target.repo_path).expanduser().resolve()}"
                outcomes.append(AuditOutcome(target.name, "SKIPPED", target.repo_path, error=error))
                report_progress(f"{target.name}: skipped; source folder was not found.")
                continue

            try:
                result = run_performance_audit(
                    target.name,
                    target.repo_path,
                    str(skill_path),
                    str(skill_root),
                    progress=report_progress,
                )
            except Exception as exc:
                error = f"Unexpected audit error: {exc}"
                outcomes.append(AuditOutcome(target.name, "FAILED", target.repo_path, error=error))
                report_progress(f"{target.name}: audit failed: {error}")
                continue
            if result.ok:
                outcomes.append(
                    AuditOutcome(
                        target.name,
                        "COMPLETED",
                        target.repo_path,
                        report_path=result.saved_path,
                    )
                )
                report_progress(f"{target.name}: audit completed; report saved to {result.saved_path}")
            else:
                outcomes.append(
                    AuditOutcome(
                        target.name,
                        "FAILED",
                        target.repo_path,
                        report_path=result.saved_path,
                        error=result.error or "No report was returned.",
                    )
                )
                report_progress(f"{target.name}: audit failed: {(result.error or 'Unknown error').splitlines()[0]}")

    finished_at = datetime.now().astimezone()
    summary = _render_summary(
        started_at,
        finished_at,
        inventory_source,
        warning,
        global_error,
        outcomes,
        log_path,
    )
    summary_path.write_text(summary, encoding="utf-8")
    (_audit_root() / "runs" / "last-run.md").write_text(summary, encoding="utf-8")

    if global_error:
        exit_code = 2
    elif warning or any(outcome.status != "COMPLETED" for outcome in outcomes):
        exit_code = 1
    else:
        exit_code = 0
    report_progress(f"Full audit finished with exit code {exit_code}. Summary: {summary_path}")
    return AuditRunResult(run_dir, summary_path, log_path, tuple(outcomes), exit_code)


def run_all_audits(progress: ProgressCallback | None = None) -> AuditRunResult:
    """Audit every application in the current manifest, continuing after failures."""
    return _run_audits(None, progress=progress)


def run_app_audit(app_name: str, progress: ProgressCallback | None = None) -> AuditRunResult:
    """Audit one application selected by its configured name."""
    return _run_audits(app_name, progress=progress)
