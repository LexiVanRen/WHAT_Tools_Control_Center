from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6 import QtCore


ProgressCallback = Callable[[str], None]


def find_codex_executable() -> str | None:
    """Find a directly launchable Codex binary (avoids Windows .cmd shims)."""
    executable = shutil.which("codex.exe")
    if executable:
        return executable
    executable = shutil.which("codex")
    if executable and Path(executable).suffix.casefold() not in {".cmd", ".bat"}:
        return executable
    return None


@dataclass(frozen=True)
class AuditResult:
    report: str = ""
    error: str = ""
    saved_path: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.report)


def _audit_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "WHATControlCenter" / "performance_audits"


def _app_dir(app_name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-") or "application"
    return _audit_root() / slug


def last_audit_path(app_name: str) -> Path | None:
    report = _app_dir(app_name) / "last-audit.md"
    return report if report.is_file() else None


def save_audit_report(app_name: str, report_text: str) -> Path:
    output_dir = _app_dir(app_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_path = output_dir / f"audit_{stamp}.md"
    content = report_text.strip() + "\n"
    report_path.write_text(content, encoding="utf-8")
    (output_dir / "last-audit.md").write_text(content, encoding="utf-8")
    return report_path


def run_performance_audit(
    app_name: str,
    repo_path: str,
    skill_path: str,
    skill_root: str,
    progress: ProgressCallback | None = None,
) -> AuditResult:
    """Run one read-only Codex performance audit and save its report."""
    repo = Path(repo_path).expanduser().resolve()
    skill = Path(skill_path).resolve()
    skills = Path(skill_root).resolve()
    project_root = skills.parent.parent.resolve()

    codex = find_codex_executable()
    if not codex:
        return AuditResult(
            error=(
                "A directly launchable Codex CLI executable was not found on PATH. "
                "Ensure `codex.exe` is available to the Windows account running this app "
                "and sign in with Codex CLI."
            )
        )
    if not repo.is_dir():
        return AuditResult(error=f"Source folder does not exist: {repo}")
    if not skill.is_file():
        return AuditResult(error=f"Audit skill was not found: {skill}")

    prompt = (
        "Use the $performance-audit skill available in this project's .agents/skills. "
        f"Audit only the application {app_name!r} at {repo}; this is the "
        "target repository. Complete every required audit pass in the skill, including a "
        "startup and packaging review. Trace launch through the first usable state, inspect "
        "the build and installer configuration (including frozen build mode and bundled "
        "dependencies), and distinguish source-launch behavior from packaged-executable "
        "behavior. Measure an existing executable when safe and available; never build one. "
        "The user authorizes launching the installed app solely to observe startup. These "
        "apps require administrator rights: first verify this audit process already has an "
        "elevated administrator token, then launch the app normally so it inherits that token. "
        "If the audit process is not elevated, skip the startup launch and report why; never "
        "invoke UAC or runas, or ask the user to approve elevation. Find and "
        "verify the matching installed executable, check that it is not already running, "
        "launch it without navigating or interacting, and measure process start to visible "
        "main window (plus input-idle when available). Do not accept prompts or initiate "
        "hardware/service actions; close only the instance you started, normally and only "
        "if no prompt appears. If the sandbox prevents launch, do not request broader access; "
        "record the limitation and continue the static review. "
        "Review every major subsystem and its important user workflows; do not stop after "
        "the first obvious hotspots or impose a finding-count cap. "
        "Follow the skill's coverage and evidence requirements, and report every distinct, "
        "actionable issue you can support. You may run the application or existing checks "
        "when safe and useful, following "
        "the skill's restrictions. Never download or install anything. Do not modify "
        "application files. Return the complete structured Markdown report required by "
        "the skill, including the required startup/packaging analysis, installed-app startup "
        "measurement (or reason unavailable), subsystem coverage table, a separate "
        "Measurement leads section for concrete unmeasured opportunities, and a tailored "
        "example AI agent prompt for each finding. Clearly distinguish measured costs, "
        "code-traceable costs, and unverified leads; state any limits and the exact validation "
        "needed."
    )
    command = [
        codex,
        "exec",
        "--model",
        "gpt-6-astra",
        "--config",
        'model_reasoning_effort="xhigh"',
        "--sandbox",
        "read-only",
        "--cd",
        str(project_root),
        "--add-dir",
        str(repo),
        "--skip-git-repo-check",
        prompt,
    ]

    def emit(message: str) -> None:
        if progress is not None:
            progress(f"{app_name}: {message}")

    emit("starting Codex performance audit...")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(project_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return AuditResult(error=f"Could not start Codex CLI: {exc}")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    reported_findings: set[str] = set()
    reported_phases: set[str] = set()
    progress_lock = threading.Lock()

    def emit_phase(message: str) -> None:
        phase = message.strip()
        with progress_lock:
            if not phase or phase.casefold() in reported_phases:
                return
            reported_phases.add(phase.casefold())
        emit(phase)

    def emit_finding(title: str) -> None:
        finding = title.strip()
        with progress_lock:
            if not finding or finding.casefold() in reported_findings:
                return
            reported_findings.add(finding.casefold())
        emit(f"found: {finding}")

    def collect_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            phase_match = re.match(r"\s*Progress:\s*(.+?)\s*$", line, re.IGNORECASE)
            if phase_match:
                emit_phase(phase_match.group(1))
                continue

            progress_match = re.match(r"\s*Found:\s*(.+?)\s*$", line, re.IGNORECASE)
            if progress_match:
                emit_finding(progress_match.group(1))
                continue

            stdout_lines.append(line)
            match = re.match(r"\s*\d+\.\s+\*\*(.+?)\*\*", line)
            if not match:
                continue
            title = match.group(1).strip().rstrip("—–- ")
            if title.lower() != "problem title":
                emit_finding(title)

    def collect_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            clean = line.strip()
            if not clean:
                continue
            phase_match = re.match(r"Progress:\s*(.+?)\s*$", clean, re.IGNORECASE)
            if phase_match:
                emit_phase(phase_match.group(1))
                continue
            progress_match = re.match(r"Found:\s*(.+?)\s*$", clean, re.IGNORECASE)
            if progress_match:
                emit_finding(progress_match.group(1))
                continue
            stderr_lines.append(clean)

    stdout_reader = threading.Thread(target=collect_stdout, daemon=True)
    stderr_reader = threading.Thread(target=collect_stderr, daemon=True)
    stdout_reader.start()
    stderr_reader.start()

    try:
        return_code = process.wait(timeout=3 * 60 * 60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        stdout_reader.join()
        stderr_reader.join()
        return AuditResult(error="The audit stopped after the three-hour time limit.")
    stdout_reader.join()
    stderr_reader.join()

    if return_code != 0:
        details = "\n".join(stderr_lines) or "".join(stdout_lines).strip()
        details = details or "Codex CLI exited without details."
        return AuditResult(error=f"Codex audit failed (exit code {return_code}).\n{details}")

    report = "".join(stdout_lines).strip()
    if not report:
        return AuditResult(error="Codex completed without returning an audit report.")

    try:
        saved = save_audit_report(app_name, report)
    except OSError as exc:
        return AuditResult(report=report, error=f"Could not save the audit report: {exc}")
    return AuditResult(report=report, saved_path=str(saved))


class PerformanceAuditWorker(QtCore.QObject):
    progress = QtCore.Signal(str)
    finished = QtCore.Signal(str, str, str)  # report, error, saved path

    def __init__(self, app_name: str, repo_path: str, skill_path: str, skill_root: str):
        super().__init__()
        self.app_name = app_name
        self.repo_path = repo_path
        self.skill_path = skill_path
        self.skill_root = skill_root

    @QtCore.Slot()
    def run(self):
        result = run_performance_audit(
            self.app_name,
            self.repo_path,
            self.skill_path,
            self.skill_root,
            progress=self.progress.emit,
        )
        self.finished.emit(result.report, result.error, result.saved_path)
