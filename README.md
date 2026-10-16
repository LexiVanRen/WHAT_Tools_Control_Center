# WHAT Tools Control Center

## Run a performance audit on every tool

From the project folder, run:

```powershell
.venv\Scripts\python.exe main.py --start_audit_all
```

The packaged application accepts the same option:

```powershell
dist\WHATControlCenter\WHATControlCenter.exe --start_audit_all
```

To audit just one configured tool, pass its name:

```powershell
.venv\Scripts\python.exe main.py --start_audit DriveDoctor
```

The compact form is also supported for app names without spaces:

```powershell
.venv\Scripts\python.exe main.py --start_audit_DriveDoctor
```

The packaged application supports both single-tool forms as well:

```powershell
dist\WHATControlCenter\WHATControlCenter.exe --start_audit DriveDoctor
dist\WHATControlCenter\WHATControlCenter.exe --start_audit_DriveDoctor
```

Tool-name matching ignores case and punctuation. If names collide after normalization,
the gateway reports the ambiguity; an unknown name fails with the available tool names.

The gateway reads the current tool list from the selected server manifest. The all-tools
option audits each configured source repository in sequence; the single-tool option
selects one configured name. If the manifest cannot be reached, it uses the locally
cached tool list and records that fallback in the run summary. A missing source folder
or an audit failure is recorded, and an all-tools run continues with the remaining tools.

Reports are saved under
`%LOCALAPPDATA%\WHATControlCenter\performance_audits`. Each tool keeps its own
timestamped report and `last-audit.md`. Full runs are saved under the `runs` folder,
with a `summary.md` and `run.log` per run and a `last-run.md` summary for the latest
run. The command exits with code 0 when every tool completes from the current manifest,
1 when a tool is skipped or fails or the cached list had to be used, and 2 when the run
cannot be set up.

For Windows Task Scheduler, use the virtual environment's `python.exe` as the program,
pass the project `main.py` path followed by `--start_audit_all` or
`--start_audit DriveDoctor` as arguments, and set the project's root folder as
**Start in**. Run it under the Windows account that is
signed in to Codex CLI. Since the audited apps require administrator rights, enable
**Run with highest privileges**. Choose **Run only when user is logged on** so the
startup check can observe the application's visible window; a non-interactive task
session cannot provide a reliable visible-window measurement.

The audit starts Codex CLI as a child process, so it inherits the task's elevated
Windows token too. The Codex sandbox remains read-only, but that does not make its
Windows token unprivileged. Keep the task limited to this audit command and the
intended Windows account.

For the packaged application, set the program to `WHATControlCenter.exe` and the
arguments to `--start_audit_all` or `--start_audit DriveDoctor`. This is a windowed
build, so its progress is written to `run.log` rather than a console window. The process
exit code remains available to Task Scheduler. Apply the same **Run with highest
privileges** and **Run only when user is logged on** settings.
