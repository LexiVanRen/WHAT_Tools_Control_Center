from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore


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


class PerformanceAuditWorker(QtCore.QObject):
    progress = QtCore.Signal(str)
    finished = QtCore.Signal(str, str, str)  # report, error, saved path

    def __init__(self, app_name: str, repo_path: str, skill_path: str, skill_root: str):
        super().__init__()
        self.app_name = app_name
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.skill_path = Path(skill_path).resolve()
        self.skill_root = Path(skill_root).resolve()
        self.project_root = self.skill_root.parent.parent.resolve()

    @QtCore.Slot()
    def run(self):
        codex = shutil.which("codex")
        if not codex:
            self.finished.emit(
                "",
                "Codex CLI was not found on PATH. Install Codex CLI, sign in with `codex`, "
                "then restart WHAT Tools Control Center.",
                "",
            )
            return

        if not self.repo_path.is_dir():
            self.finished.emit("", f"Source folder does not exist: {self.repo_path}", "")
            return
        if not self.skill_path.is_file():
            self.finished.emit("", f"Audit skill was not found: {self.skill_path}", "")
            return

        prompt = (
            "Use the $performance-audit skill available in this project's .agents/skills. "
            f"Audit only the application {self.app_name!r} at {self.repo_path}; this is the "
            "target repository. Perform a thorough multi-pass review of all major application "
            "subsystems; do not stop after the first few findings or impose a finding-count cap. "
            "Follow the skill's coverage and evidence requirements, and report every distinct, "
            "actionable issue you can support. You may run the application or existing checks "
            "when safe and useful, following "
            "the skill's restrictions. Never download or install anything. Do not modify "
            "application files. Return the complete structured Markdown report required by "
            "the skill, including a tailored example AI agent prompt for each finding. "
            "Clearly distinguish measurements from code-based hypotheses and state any limits."
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
            str(self.project_root),
            "--add-dir",
            str(self.repo_path),
            "--skip-git-repo-check",
            prompt,
        ]
        self.progress.emit(f"{self.app_name}: starting Codex performance audit…")

        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                # The complete prompt is already an argv argument. Close stdin so
                # Codex does not wait for more prompt text from the GUI's parent.
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
            self.finished.emit("", f"Could not start Codex CLI: {exc}", "")
            return

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        reported_findings: set[str] = set()
        reported_phases: set[str] = set()
        progress_lock = threading.Lock()

        def emit_phase(message: str):
            phase = message.strip()
            with progress_lock:
                if not phase or phase.casefold() in reported_phases:
                    return
                reported_phases.add(phase.casefold())
            self.progress.emit(f"{self.app_name}: {phase}")

        def emit_finding(title: str):
            finding = title.strip()
            with progress_lock:
                if not finding or finding.casefold() in reported_findings:
                    return
                reported_findings.add(finding.casefold())
            self.progress.emit(f"{self.app_name}: found: {finding}")

        def collect_stdout():
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

        def collect_stderr():
            assert process.stderr is not None
            for line in process.stderr:
                clean = line.strip()
                if clean:
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
            self.finished.emit("", "The audit stopped after the three-hour time limit.", "")
            return
        stdout_reader.join()
        stderr_reader.join()

        if return_code != 0:
            details = "\n".join(stderr_lines) or "".join(stdout_lines).strip()
            details = details or "Codex CLI exited without details."
            self.finished.emit("", f"Codex audit failed (exit code {return_code}).\n{details}", "")
            return

        report = "".join(stdout_lines).strip()
        if not report:
            self.finished.emit("", "Codex completed without returning an audit report.", "")
            return

        try:
            saved = save_audit_report(self.app_name, report)
        except OSError as exc:
            self.finished.emit(report, f"Could not save the audit report: {exc}", "")
            return
        self.finished.emit(report, "", str(saved))
