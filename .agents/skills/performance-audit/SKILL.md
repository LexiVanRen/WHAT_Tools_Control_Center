---
name: performance-audit
description: Audit an application's source and safe, reproducible runtime behavior for performance problems, inefficient or poor coding patterns, and practical optimization opportunities. Use when the user requests a performance, code efficiency, or optimization review.
---

# Application performance audit

Investigate the application as it exists, with code analysis as the main focus. Look for performance problems and coding patterns that create unnecessary work, resource use, or complexity, then identify practical code optimizations. Keep code quality observations tied to concrete effects or maintainability risks; avoid subjective style criticism. Separate measured or clearly traceable problems from optimization opportunities that need measurement. Produce an evidence-based report that helps its maintainer decide what to improve first. Do not make source changes during an audit.

## Investigation

1. Map the repository before judging it. Identify the language, entry points, UI framework, major data flows, persistence and network operations, background work, and how users reach the important features. Read project guidance and relevant documentation in the repository.
2. Trace expensive user-visible paths end to end. Look for work on the UI thread, repeated or duplicated work, avoidable disk or network access, inefficient algorithms, data structures or queries, excess rendering, synchronous waits, leaks, unbounded growth, and costly startup initialization. Also note concrete code patterns that make these paths unnecessarily hard to optimize or maintain. Explain the actual execution path and cost for each suspected issue, and frame unmeasured ideas as optimization opportunities rather than proven bottlenecks.
3. Check available project commands and existing tests. Run focused, relevant checks when dependencies are already installed and the commands are safe. Never download or install programs, packages, dependencies, SDKs, runtimes, extensions, or other tools. Do not build installers or executables, alter configuration, or change application data.
4. You may run the application to investigate startup, idle resource use, and feature timings. Prefer existing automated tests, benchmark commands, or documented development launch commands. A GUI may be started only when an existing source-run command or already-built application is clear; never build an executable or installer to run it. Use a disposable/test mode or data when available. Avoid production services and destructive actions. If a real user workflow cannot be exercised with available tools, say so and describe the missing workload or interaction.
5. Measure when practical: record the command, scenario, duration, and available CPU, memory, or operation timings. Separate measured evidence from static reasoning. Do not invent benchmarks or claim that an unmeasured path is slow.

## Audit depth and coverage

- Review the whole application source in deliberate passes. First map the repository and identify generated, vendored, or irrelevant directories to exclude. Then review each major application subsystem and its important user workflows, following calls across UI, services, data access, persistence, and background work. Do not infer that a large repository has been covered after reading only its entry points or a few obvious hotspots.
- Use repository searches and available static-analysis tools to find repeated work, expensive loops, blocking calls, unbounded collections, duplicated implementations, risky resource handling, and other concrete optimization opportunities. Read the surrounding code before deciding that a search hit is a finding.
- Keep a private coverage checklist as you work. Before finishing, check which major subsystems remain unreviewed, revisit promising paths, and validate candidate findings against callers, data sizes, and relevant existing checks when possible.
- There is no finding-count target or cap. Report every distinct, actionable, evidence-supported issue you found, including lower-priority optimization opportunities when useful. Do not invent or split findings to increase the count, and do not stop early just because a few findings are clear.
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
- Coverage summary naming the major subsystems and workflows reviewed, plus exclusions or areas left unreviewed and why.
- Checks that found no issue only when useful to explain coverage.
- Limitations, assumptions, and any workflow that needs a human to exercise.

Keep findings specific and actionable. Cite evidence from the repository; distinguish measured facts, code-traceable inefficiencies, and likely bottlenecks. Include practical optimization directions that preserve existing behavior and constraints. Do not recommend broad rewrites or style-only changes without evidence.
