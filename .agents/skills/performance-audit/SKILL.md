---
name: performance-audit
description: Audit an application's source and safe, reproducible runtime behavior for performance problems, inefficient or poor coding patterns, and practical optimization opportunities. Use when the user requests a performance, code efficiency, or optimization review.
---

# Application performance audit

Investigate the application as it exists, with code analysis as the main focus. Look for performance problems and coding patterns that create unnecessary work, resource use, or complexity, then identify practical code optimizations. Keep code quality observations tied to concrete effects or maintainability risks; avoid subjective style criticism. Separate measured or clearly traceable problems from optimization opportunities that need measurement. Produce an evidence-based report that helps its maintainer decide what to improve first. Do not make source changes during an audit.

## Investigation

1. Map the repository before judging it. Identify the language, entry points, UI framework, major data flows, persistence and network operations, background work, and how users reach the important features. Read project guidance and relevant documentation in the repository.
2. Trace expensive user-visible paths end to end. Look for work on the UI thread, repeated or duplicated work, avoidable disk or network access, inefficient algorithms, data structures or queries, excess rendering, synchronous waits, leaks, unbounded growth, and costly startup initialization. Also note concrete code patterns that make these paths unnecessarily hard to optimize or maintain. Explain the actual execution path and cost for each suspected issue, and frame unmeasured ideas as optimization opportunities rather than proven bottlenecks.
3. Inspect how the application is built and packaged. Search build scripts, project/package manifests, PyInstaller `.spec` files, installer definitions, CI configuration, and launch scripts. Trace what actually runs in a packaged build, how dependencies and data files are bundled, and whether startup includes extraction, scanning, duplicated packaging layers, or work that differs from a source launch. Check both the application and its shipped launcher/build path when they are in scope. Do not assume packaging is irrelevant because the source code looks efficient.
4. Check available project commands and existing tests. Run focused, relevant checks when dependencies are already installed and the commands are safe. Never download or install programs, packages, dependencies, SDKs, runtimes, extensions, or other tools. Do not build installers or executables, alter configuration, or change application data.
5. You may run the application to investigate startup, idle resource use, and feature timings. Prefer existing automated tests, benchmark commands, or documented launch commands. When the user has authorized launching installed apps, an existing installed executable is an approved startup-test target even when no source-run command is available. Never build an executable or installer to run it. Use a disposable/test mode or data when available. Avoid production services and destructive actions. If a real user workflow cannot be exercised safely, say so and describe the missing workload or interaction. A source launch does not establish packaged-application startup performance; measure an existing packaged build separately when safe and available.
6. Measure when practical: record the command, scenario, fresh-process or repeat launch, duration, and available CPU, memory, or operation timings. For startup, record process launch to the first visible main window and, when possible, to an input-idle/ready state. State exactly how “ready” was detected; a visible window is not proof that every feature is ready. Do not call a fresh process a cold OS start unless system caches were actually cold. Separate measured evidence from static reasoning. Do not invent benchmarks or claim that an unmeasured path is slow.

## Installed application startup check

When the user has authorized launching installed applications, perform this check for each target when a matching installed executable can be identified safely:

- Find the executable from an app-specific Start Menu shortcut, installed-app registry entry, or a clearly matching installation path. Verify its product/app identity against the audited tool. Do not choose an installer, an unrelated executable with a similar name, or a development build as a substitute for the installed app.
- These applications require administrator rights. Check that the current process already has an elevated administrator token before launching; for example, use PowerShell's `WindowsPrincipal.IsInRole(WindowsBuiltInRole.Administrator)` rather than inferring elevation from account membership. Start the app normally so it inherits that token. If the audit process is not elevated, record that the startup measurement was skipped; do not invoke UAC, use `runas`, or ask the user to approve an elevation prompt.
- Check whether the application is already running. Do not close or interfere with an existing user process, and do not launch a second instance if that could replace or disturb it. If it is already running, report that a fresh startup measurement was unavailable.
- Start only the identified executable with its normal launch arguments. Record the process start time, executable path, and elapsed time until the main application window is visible. If a launcher starts a child process, identify and observe the process that owns the UI window. When practical, also note when the process reaches input idle. Poll window/process state using available built-in tools; do not install measurement libraries.
- Do not navigate, click controls, type into the application, open menus, select files, connect/disconnect hardware, or exercise workflows. Observe startup only. If a UAC prompt appears despite the elevated token, or if sign-in, first-run, update, or another prompt appears, stop the check and report it without approving the prompt. If startup automatically initiates hardware communication or a production action, stop the check and report what happened.
- After the window remains visible for about two seconds, close only the process launched by this audit through its normal close path if it can close without a prompt or data-changing action. Never force-kill an existing user process. If a prompt appears or normal close is uncertain, leave the app untouched and report that it remains open.
- Respect the active sandbox. If it prevents launching the installed executable or blocks normal startup writes, do not weaken the sandbox or retry with broader access. Record the exact limitation; retain the static startup/packaging analysis and identify what a human-run measurement would need.

## Required audit passes

Complete these passes before writing the report. Adapt the named subsystems to the project, but do not silently omit a pass. If a pass does not apply or cannot be completed, explain why.

1. **Repository and launch map:** identify entry points, major modules, generated/vendor directories to exclude, user workflows, and the route from launch to ready state.
2. **Startup and packaging:** trace top-level imports, initialization, configuration and data loading, hardware or service discovery, window creation, and the first ready/interactive point. Inspect packaging and launcher configuration. For frozen applications, identify the actual mode and relevant settings (for example, one-file versus one-directory, extraction behavior, bundled data, and external dependencies). Treat expected costs as hypotheses unless measured.
3. **Subsystem coverage:** inspect each major subsystem and at least one important end-to-end path through its callers and dependencies. Include the user-visible workflow most likely to be performance-sensitive, not just the largest or easiest file.
4. **Search and runtime evidence:** search for blocking calls, repeated work, expensive loops, unbounded growth, import-time work, and avoidable I/O. Inspect every promising hit in context. Run only safe existing checks or workloads; when the user has authorized installed-app launch, perform the installed application startup check. Record what ran and what did not.
5. **Candidate validation:** revisit each candidate against its callers, data sizes, execution frequency, and user impact. Distinguish measured bottlenecks, code-traceable costs, and concrete leads that still need a measurement. Do not suppress a useful lead merely because hardware or a production workflow is unavailable; label its uncertainty and state the exact validation needed.
6. **Coverage review:** compare the work completed with the launch map and subsystem list. Revisit omissions before finishing. The report must expose coverage so the maintainer can see what received attention and what did not.

## Audit depth and coverage

- Review the whole application source in deliberate passes. First map the repository and identify generated, vendored, or irrelevant directories to exclude. Then review each major application subsystem and its important user workflows, following calls across UI, services, data access, persistence, and background work. Do not infer that a large repository has been covered after reading only its entry points or a few obvious hotspots.
- Include build and packaging configuration in the review. A startup complaint can originate in the launcher, packaging mode, dependency collection, extraction, import order, or initialization path. If the reported symptom concerns an existing executable, inspect that executable's build configuration and, when an existing artifact can be run safely, measure that artifact. Never build a new artifact during the audit.
- Use repository searches and available static-analysis tools to find repeated work, expensive loops, blocking calls, unbounded collections, duplicated implementations, risky resource handling, and other concrete optimization opportunities. Read the surrounding code before deciding that a search hit is a finding.
- Keep a private coverage checklist as you work. Before finishing, check which major subsystems remain unreviewed, revisit promising paths, and validate candidate findings against callers, data sizes, and relevant existing checks when possible.
- There is no finding-count target or cap. Report every distinct, actionable, evidence-supported issue you found, including lower-priority optimization opportunities when useful. Do not invent or split findings to increase the count, and do not stop early just because a few findings are clear.
- Do not narrow the investigation to the first obvious hotspots or to the application's primary algorithm. Continue through startup/packaging, major subsystems, recurring work, data and hardware I/O, and resource lifetimes. If a subsystem was reviewed and no issue was found, show that coverage briefly rather than inventing a complaint for it.
- Include a separate **Measurement leads** section for concrete, potentially important costs that code or build configuration makes plausible but that could not be confirmed safely. For each lead, give the evidence, why it could matter, confidence, and the exact scenario or measurement needed. Do not present these as confirmed findings or pad the section with generic suggestions.
- In the report, state which major subsystems and workflows you reviewed, what you excluded, and any areas you could not inspect. Keep recommendations specific to the evidence; code quality concerns must connect to a concrete performance, reliability, or maintenance impact.

## Progress updates

Give brief progress updates as work advances: `Progress: Mapping repository`, `Progress: Reviewing <subsystem> (<current>/<total>)`, `Progress: Tracing performance paths`, `Progress: Checking runtime behavior`, `Progress: Validating findings`, and `Progress: Preparing report`. Use subsystem names for the review updates, and avoid repeating a phase update. Skip runtime behavior if it cannot be checked and say why in the final report. Avoid routine tool narration.

As soon as you have enough evidence to report a finding, send one concise standalone progress line in this exact format: `Found: <short finding title>`. Emit each finding once, as you identify it, and continue the investigation afterward. Do not emit speculative issues. Keep all `Progress:` and `Found:` lines out of the final Markdown report; include each finding in the report's structured findings section instead.

## Report

Return a well-structured Markdown report with:

- Application, repository, audit date, and audit method.
- A short overall assessment and the highest-value next action.
- Findings ordered by priority (P1 first), each using this structure:
  1. **Problem title** — short and specific.
  2. **Priority / severity / confidence** — use P1 (highest), P2, P3; High, Medium, or Low; and High, Medium, or Low confidence.
  3. **Explanation** — describe the execution or data flow, why it costs time or resources, and its likely user impact. Include precise repository references as `path/to/file.ext:line` and distinguish measured evidence from code-based hypotheses.
  4. **Suggested direction** — a concise, concrete improvement, without changing the code during the audit.
  5. **Example AI agent fix prompt** — provide a ready-to-copy prompt tailored to that finding. Tell the coding agent which references to inspect, what performance behavior to improve, what constraints to preserve, and to verify the change with relevant existing checks. Do not present the prompt as proof that the fix is correct.
- Runtime checks and measurements, including commands/scenarios and results, or a clear note that runtime behavior could not be measured.
- A **Startup and packaging analysis** summarizing the launch path through the first usable state, the relevant build/package settings, and any cold/warm startup measurements. If measurements or an existing packaged artifact are unavailable, state the exact limitation and the next safe validation step.
- An **Installed application startup measurement** for each app successfully launched: installed executable path, whether the process was already running, whether the audit process had an elevated administrator token, process-start-to-visible-window duration, ready-state detection, and whether the audit closed the process. Mark unavailable measurements and their reason. Do not imply that a source-only run measures the installed executable.
- A concise coverage table naming each major subsystem or audit pass, the key paths/configuration examined, and whether it was reviewed, partly reviewed, or excluded (with the reason). Do not claim whole-repository coverage without this evidence.
- A separate **Measurement leads** section for substantiated but unmeasured opportunities, if any. State what code/configuration supports the lead and how to validate it. Omit this section when there are no concrete leads.
- Exclusions and areas left unreviewed, with reasons and their effect on confidence.
- Checks that found no issue only when useful to explain coverage.
- Limitations, assumptions, and any workflow that needs a human to exercise.

Keep findings specific and actionable. Cite evidence from the repository; distinguish measured facts, code-traceable inefficiencies, and likely bottlenecks. Include practical optimization directions that preserve existing behavior and constraints. Do not recommend broad rewrites or style-only changes without evidence.
