# AGENTS.md — HookDoctor development contract

> Revision: v0.3, 2026-10-10.
> Status: implementation contract for the capstone topic-change proposal. The CLI is not yet implemented or accepted.
> Course: Chung-Ang University Capstone Design (1), section 5, team 8.
> Midterm: 2026-10-16, 10-minute presentation plus 5-minute Q&A.
> Final demonstration: 2026-12-11.
> Repository organization when authorized: https://github.com/CAU-2026-2-capstone-5-team-8

## 1. Authority, objective and boundaries

This file defines the v0.3 implementation and acceptance contract. For implementation details, use it instead of conflicting v0.2 examples in the proposal, slides or older copies of AGENTS.md. Follow the user's current instructions and higher-priority platform instructions first. The Markdown file and its Google Docs editing copy must contain the same contract text when updated together.

Build HookDoctor, a small Linux CLI that helps a C/C++ developer investigate why LD_PRELOAD interception appears not to work. Given one preload library, one expected dynamic symbol and a target argv, correlate ELF import/export facts with glibc loader observations, state what those observations establish, identify conditional explanations and suggest the next check. The product is a developer debugging tool.

The midterm deliverable is a working CLI, reproducible fixtures, evidence, tests and a short demonstration. Do not add a GUI, server, database, daemon, eBPF, kernel instrumentation, automatic code repair or universal interception. Keep the analysis model separate from terminal/JSON rendering so a later frontend can reuse it.

Preserve the original book-recommendation repositories. Work in the user-designated HookDoctor directory or an isolated local directory when none exists. A request to start development authorizes the necessary local implementation and verification. Do not repeatedly ask for permission for those steps. Creating a remote repository, pushing or publishing requires authorization for that action; honor authorization already present in the session. Team/professor topic approval is a project milestone and does not block authorized local prototype work.

## 2. Supported environment and limits of the evidence

- Initial platform: Linux x86-64, glibc loader, GCC/cc, GNU readelf and nm, Make, Python 3.11 or newer. Use the Python standard library for the core and unittest.
- Require an explicit ELF executable path, one readable ELF shared library and target arguments. Shell scripts, launchers resolved through PATH, other architectures/loaders and child-process diagnosis are outside the midterm support contract. Report the limitation instead of guessing.
- Inspect every compiled ELF. Headers, compiler flags, optimization, libc and ABI can change symbol references. The fixture contract requires observed imports of open and open64; a failed assumption is a blocked fixture, not a passing test.
- Distinguish four things: a library was loaded, a symbol is exported, a symbol was bound to an object, and a function body actually ran.
- LD_DEBUG binding events can occur during eager relocation before a function is called. An import and a binding do not prove invocation. A missing hook marker does not prove failure.
- The generic check command has no function-entry observer in this MVP. Its observations.invocation is always UNKNOWN. Only the controlled test/demo harness may use fixture source, selected arguments and known markers as invocation ground truth.
- Conventional fully static ELF executables are outside the glibc preload mechanism. Secure execution, static PIE, unusual symbol scopes and unsupported loader output require conservative handling as specified below.

## 3. Midterm acceptance gates

All of the following are MUST requirements, including validation, timeouts and real output bounds. They are not optional hardening after the demo.

1. Build app_normal and app_large from the same fixtures/app.c. Confirm their dynamic imports are open and open64 respectively.
2. Show successful target execution with an open-only hook in both cases: app_normal emits the open marker; app_large emits neither hook marker.
3. Manually build a corrected hook exporting both open and open64. Run the unchanged app_large and the same argv with that hook; the open64 marker and target success must appear. HookDoctor itself does not modify code.
4. Correlate dynamic ELF imports/exports with target-origin runtime binding. Report SYMBOL_VARIANT_MISMATCH as a CONDITIONAL explanation under the exact rule in section 8. Do not claim the current workload's failure was proved.
5. Test an eager-binding executable with both --call and --skip. The generic engine must not invent different invocation knowledge from the binding logs. The harness must independently distinguish the two code paths.
6. Demonstrate one secondary case: a verified conventional static executable, or a valid shared library missing the requested export if static compilation is unavailable. Record the actual selection and reason.
7. Provide help, version, bounded execution, clear terminal output, one stable JSON report, unittest coverage and scripts/demo.sh. The main demo must finish within two minutes without root.
8. Preserve commands, toolchain details, raw evidence and actual test results in docs/EVIDENCE.md. Mark unsupported/skipped checks with reasons. Do not describe a reference experiment as a completed HookDoctor implementation.

Freeze new diagnosis families on 2026-10-14. Packaging polish, broad platform support, CI and a frontend do not take priority over these gates.

## 4. Fixtures and their ground truth

Use one app.c and one hook.c to make the build differences easy to review. Required files:

```text
fixtures/app.c
fixtures/app_conditional.c
fixtures/hook.c
fixtures/hook_no_export.c
fixtures/Makefile
fixtures/expected_cases.json
```

app.c calls open("/dev/null", O_RDONLY), checks the result, closes the descriptor, prints exactly "target: success" on success and returns nonzero on failure. Do not use source conditionals to switch between open and open64. Build from the repository root:

```bash
cc -O2 fixtures/app.c -o fixtures/app_normal
cc -O2 -D_FILE_OFFSET_BITS=64 fixtures/app.c -o fixtures/app_large
cc -shared -fPIC fixtures/hook.c -o fixtures/libhook_open.so -ldl
cc -shared -fPIC -DWITH_OPEN64 fixtures/hook.c -o fixtures/libhook_fixed.so -ldl
cc -O2 -D_FILE_OFFSET_BITS=64 fixtures/app_conditional.c -Wl,-z,now -o fixtures/app_conditional_now
cc -shared -fPIC fixtures/hook_no_export.c -o fixtures/libhook_no_export.so
```

hook.c uses _GNU_SOURCE and the correct variadic signatures. The ordinary build exports open only; WITH_OPEN64 exports both open and open64. Resolve each original with dlsym(RTLD_NEXT, the same symbol name), check resolution failure and forward correctly. Only consume a mode argument when flags require it, including O_CREAT or the complete O_TMPFILE flag combination where available. Preserve target-visible return values and errno around diagnostic output. Use a simple stderr marker without file-opening recursion:

```text
[HOOK] open intercepted
[HOOK] open64 intercepted
```

These are controlled, single-thread fixture wrappers, not a production-ready general interposition library. hook_no_export.c exports an unrelated harmless symbol and neither open nor open64.

app_conditional.c accepts exactly --call or --skip. It contains an open call on the --call branch and performs no open call on the --skip branch. Both successful branches print distinguishable deterministic completion lines. Build this source once with large-file flags and -Wl,-z,now. Confirm its open64 import and eager relocation metadata. Use that SAME binary for both arguments and both preload libraries. A separate program that has no relevant import does not satisfy the no-call gate.

Makefile's default all target builds the six required dynamic artifacts above without requiring static development libraries. The displayed commands run from the repository root; Makefile recipes run inside fixtures with make -C fixtures and use names such as app.c and app_normal without another fixtures/ prefix. A separate static target attempts cc -O2 -static app.c -o app_static there. Accept the static case only after the ELF checks in section 7. If static build support is absent, record the compiler failure, mark that test SKIPPED and use the no-export library as the required secondary demo. Never generate a substitute file and call it static.

Collect evidence with dynamic symbol commands, not an unrestricted full symbol table:

```bash
readelf --wide --dyn-syms fixtures/app_normal
readelf --wide --dyn-syms fixtures/app_large
readelf --wide -h -l -d fixtures/app_conditional_now
nm -D --defined-only fixtures/libhook_open.so
nm -D --defined-only fixtures/libhook_fixed.so
```

The harness executes fixtures with an explicit clean loader environment, an absolute LD_PRELOAD path and LD_DEBUG=libs,bindings when collecting runtime evidence. Record exact argv and environment overrides. Preserve the hash of app_large before and after the hook repair demonstration.

The review on 2026-10-10 reproduced the main scenario and eager no-call behavior on Ubuntu 24.04.3 x86-64, GCC 13.3, glibc 2.39 and GNU binutils 2.42. The observed compiler defaults included eager binding. This establishes the fixture's feasibility, not the correctness of code still to be written. Reproduce on the team's development environment and record its actual configuration.

## 5. CLI and process contract

Required public interface:

```bash
hookdoc --help
hookdoc --version
hookdoc check --lib ./fixtures/libhook_open.so --symbol open -- ./fixtures/app_large
hookdoc check --lib ./fixtures/libhook_open.so --symbol open --json -- ./fixtures/app_large
hookdoc check --lib ./fixtures/libhook_fixed.so --symbol open64 -- ./fixtures/app_large
hookdoc check --lib ./fixtures/libhook_open.so --symbol open --timeout 10 --max-output-bytes 5242880 -- ./fixtures/app_large
```

Also provide the identical interface through PYTHONPATH=src python3 -m hookdoctor so development does not depend on an editable install or network access. Define the hookdoc console entry point in pyproject.toml. Version is 0.3.0 for the initial implementation of this contract; schema_version is the string "0.3".

--symbol is one exact, unversioned dynamic symbol name, such as open or open64. It is not a symbol family or a source-level API description. Reject an empty name, whitespace or a version suffix in this option. Preserve version information found in ELF/logs as evidence. After the repair, use --symbol open64 to check the expected app_large binding. The unchanged workload requirement applies to the target binary and argv, not to that diagnostic option.

Everything after the mandatory -- separator is the target argv array, with a nonempty executable element. Never use shell=True or concatenate argv into a shell command. Run the target at most once per check, with its original working directory, stdin from DEVNULL and captured stdout/stderr. Do not perform an automatic baseline run, repair or rerun. A user invoking check is requesting this bounded target execution.

Human output must separately label Observed facts, Conditional explanations and Remaining uncertainty. Lead with useful facts such as "Requested symbol bound to the hook: confirmed" when present. Explain that overall INCONCLUSIVE concerns the current workload's cause, not the validity of every observed fact. Show inputs, inspection outcome, target-origin binding, relevant evidence references, target exit status and the next check.

Exit codes are fixed:

| Code | Meaning |
| --- | --- |
| 0 | Analysis completed, including conditional/inconclusive results, confirmed facts or a supported static result |
| 2 | CLI syntax error or invalid option value; timeout must be finite and positive, and output limit must be a positive integer; reject before launching subprocesses |
| 3 | Invalid/missing input, unsupported platform/ELF, required collector failure or failure to launch the target |
| 4 | Target or required collector timeout |
| 5 | Captured output limit reached |

A target's nonzero exit or signal does not by itself change HookDoctor's exit code from 0. Preserve it in run.target_exit_code and state it in the report. This separates program behavior from whether analysis completed. Missing requested exports in a valid, inspected library are findings, not infrastructure errors. A missing library path is an input error.

After valid parsing of a check request, --json writes exactly one JSON document to stdout on every outcome, including codes 3, 4 and 5. Capture target output instead of streaming it before or after the JSON. CLI parsing errors may use stderr only and code 2. Put progress messages on stderr; normal JSON mode needs no progress messages. Every report includes the fields in section 9, using null/empty lists where collection did not occur.

## 6. Minimal code organization and data flow

```text
AGENTS.md
README.md
pyproject.toml
src/hookdoctor/__init__.py
src/hookdoctor/__main__.py
src/hookdoctor/cli.py
src/hookdoctor/models.py
src/hookdoctor/inspector.py
src/hookdoctor/tracer.py
src/hookdoctor/diagnose.py
src/hookdoctor/reporting.py
fixtures/  (section 4)
tests/test_fixtures.py
tests/test_inspector.py
tests/test_tracer.py
tests/test_diagnosis.py
tests/test_cli.py
scripts/demo.sh
docs/EVIDENCE.md
docs/SOURCES.md
```

Use small standard-library dataclasses or equivalent typed structures. cli builds a request; inspector and tracer return observations/evidence; diagnose applies pure rules; reporting renders the same report to terminal or JSON. Avoid duplicated rule logic in the renderer. Generate stable evidence references and resolve every reference before rendering.

expected_cases.json belongs to the test/demo harness only. Production modules must not read it, inspect fixture filenames to select answers or recognize known target/marker strings as proof of invocation. Do not hardcode expected library paths, compiler versions, PIDs or libc addresses. Keep all project code in one repository when remote work is authorized.

## 7. Collection, attribution and execution bounds

### 7.1 Preflight and ELF inspection

- Resolve input paths without shell expansion. Require a regular, readable target file with execute permission and a regular, readable hook file. The hook does not need its execute bit. Reject hook paths containing whitespace or a colon because a single LD_PRELOAD entry cannot represent those separators unambiguously.
- Verify Linux x86-64/glibc support and required tool availability before launching. Inspect ELF headers, program headers, dynamic section and dynamic symbol table with successful, bounded GNU readelf calls; cross-check hook exports with nm -D --defined-only. Collect ELF type/class/machine, PT_INTERP, PT_DYNAMIC, DT_NEEDED and eager-binding flags.
- Target and hook must have compatible class and machine. The hook must be a supported ET_DYN shared object. An ordinary dynamic target must have a supported glibc PT_INTERP. Reject known secure-execution cases, including set-user-ID/set-group-ID targets, as unsupported; do not promise complete detection of all secure-execution causes.
- Dynamic imports are undefined dynamic symbols. Exports used as evidence must be defined, externally visible dynamic symbols, accounting for binding/visibility and version metadata. Preserve the raw name and its version. Comparing base names may strip a recognized @/@@ version decoration, but must not assert version compatibility from that alone.
- A missing-symbol fact requires successful complete inspection of the relevant dynamic symbol table. A failed command, unrecognized output or truncated table is not proof of absence.
- STATIC_EXECUTABLE is allowed only after successful ELF inspection confirms an ET_EXEC target with no PT_INTERP, no PT_DYNAMIC and no DT_NEEDED. Skip target execution and return NOT_APPLICABLE, code 0. ET_EXEC alone is insufficient. ET_DYN without PT_INTERP does not establish this result; report unsupported/ambiguous ELF with code 3. Static PIE support is deferred.

### 7.2 Loader environment and provenance

- Use separate environments for collectors and the target. For readelf/nm and other helper probes, remove inherited LD_* variables and set LC_ALL=C. Never preload the hook into diagnostic subprocesses.
- The target inherits ordinary environment variables, but explicitly replace LD_PRELOAD with the single requested absolute hook path and set LD_DEBUG=libs,bindings. Remove inherited LD_AUDIT, LD_DEBUG_OUTPUT and LD_TRACE_LOADED_OBJECTS. Record this policy and the relevant changes in run.loader_environment.
- Preserve existing LD_LIBRARY_PATH and LD_BIND_NOW and record their effective values, using null when absent. Do not silently force lazy binding or add a second inherited preload library. Fixture tests instead clear inherited LD_* settings so their environment is repeatable.
- Do not serialize the entire environment. Capture loader output from stderr; do not use LD_DEBUG_OUTPUT in the MVP. Keep raw excerpts and parse only recognized loader formats. Target stderr can share that stream, so it is not an authenticated telemetry channel.
- A binding event contains pid, caller_object, symbol, symbol_version, provider_object and evidence_ids. Identify the direct target PID and resolve logged object paths conservatively against the launched executable/library. Compare canonical object identity when available, not a substring of a filename. If attribution cannot be established, retain raw evidence and report UNKNOWN for that conclusion.
- Only the direct target PID with caller_object equal to the inspected target may support the main mismatch rule. A hook-to-libc RTLD_NEXT binding is normal forwarding, not target bypass. Retain child/other-object events as raw evidence if useful, but exclude them from the MVP diagnosis rule.
- LIBRARY_LOADED requires a positive, recognized event from the directly launched target PID establishing that the requested object was loaded, such as its initialization or it being the provider of an attributed binding. An attempted search/open alone is insufficient. No observed load event means UNKNOWN, not false.

### 7.3 Time, output and cleanup

- Default target timeout is 10 seconds, configurable with --timeout. Accept only finite positive numbers; reject NaN and infinity as CLI option errors. Each helper command has a 5-second timeout. These bounds are mandatory from the first executable CLI.
- Default --max-output-bytes is 5242880 (5 MiB). Apply a hard cap to stdout plus stderr captured from each subprocess. Read incrementally; stop before retaining bytes over the cap. Do not read unbounded data into memory or disk and truncate it afterward. Keep the report's raw excerpts bounded too.
- Launch each managed subprocess in a new session/process group. On its timeout or output limit, terminate only the group created for that subprocess, allow a short 0.5-second grace period, then kill if needed and reap it. The deadline also covers stream draining after the direct process exits; a child holding a pipe open must not disable the timeout. Never kill an unrelated pre-existing process group.
- Record partial evidence, code 4 or 5 and status ERROR for a limit hit. run.trace_complete is true only when the target run ended, all its captured streams reached EOF within the bounds and collection completed without truncation. A complete trace still does not prove invocation or absence of an unrecognized event.
- Use a finally path to clean owned temporary files and process groups on success, failure and caught interruption/cancellation. Do not modify /etc/ld.so.preload, global loader configuration, services or privileged processes. The tool runs as the current user and is not a malware sandbox. Project fixtures must not read private keys or capture sensitive buffers.

## 8. Facts, explanations and rule conditions

Use one vocabulary everywhere. Retire LIKELY, UNDETERMINED, HOOK_BINDING_OBSERVED, numeric confidence, evidence.observation and singular next_step from the v0.2 draft. The canonical binding success code is EXPECTED_BINDING_OBSERVED; evidence text uses summary; diagnosis guidance uses next_steps.

| Location | Allowed status | Meaning |
| --- | --- | --- |
| report.status | INCONCLUSIVE | Collection completed for a supported dynamic target; invocation and the actual workload cause remain unresolved |
| report.status | NOT_APPLICABLE | Confirmed conventional static executable; no target run |
| report.status | ERROR | Input, platform, collector, launch, timeout or output-limit error prevented complete analysis |
| facts[].status | CONFIRMED | Direct fact supported by the referenced successful observation |
| diagnoses[].status | CONDITIONAL | Explanation that depends on an explicitly stated unobserved condition |

Generic check always sets observations.invocation to UNKNOWN, including normal and fixed fixtures. Use observations.library_load = OBSERVED, UNKNOWN or NOT_RUN. A recognized binding belongs in observations.bindings; an empty list means no qualifying event was observed, not that a function never ran. Any report with INCONCLUSIVE must explain this limitation clearly. Do not put INCONCLUSIVE into diagnoses as a catch-all rule.

Canonical fact codes: LIBRARY_NOT_FOUND, STATIC_EXECUTABLE, TARGET_IMPORTS_SYMBOL, HOOK_EXPORTS_SYMBOL, SYMBOL_NOT_EXPORTED, LIBRARY_LOADED, BINDING_OBSERVED and EXPECTED_BINDING_OBSERVED. Use unique fact IDs separately from these codes. Export facts identify the symbol and the inspected library in their message/evidence; version constraints stay visible. Input/collector failures belong in errors, with an additional fact only when directly established.

EXPECTED_BINDING_OBSERVED requires the directly launched target to bind the exact requested symbol to the requested hook object in a recognized event, with raw version information retained. This confirms symbol resolution, not wrapper entry, correct behavior or end-to-end success. Do not emit it for hook-to-libc forwarding.

For the midterm, SYMBOL_VARIANT_MISMATCH is the only primary explanation family. Emit it only when all conditions hold:

1. The request is --symbol open. The explicit supported variant map is {"open": ["open64"]}; do not infer other suffix relationships.
2. Successful complete ELF inspection shows that the target imports open64, the requested hook exports open, and that hook does not export open64.
3. A recognized event from the direct target PID shows that the target's open64 resolves to an identified libc object, rather than the requested hook. Attribution, the symbol name and provider identity must all be established.
4. The relevant collection is complete and not timed out, failed or truncated. Preserve version metadata; do not substitute a version-mismatch explanation without a separate supported rule.

The diagnosis has status CONDITIONAL and condition: "If this workload executes the observed open64 path, a hook exporting only open cannot intercept that open64 call." Its message states the observed import/export/binding mismatch, and next_steps recommends adding a correct open64 wrapper, then rerunning the same workload with --symbol open64. Never write "the function was called", "the hook failed in this run" or "the compiler used _FILE_OFFSET_BITS=64" as a generic confirmed fact from this evidence alone.

If runtime binding cannot be attributed, keep the static facts and overall INCONCLUSIVE without this runtime-correlated diagnosis. If valid inspection shows a requested export is missing, emit SYMBOL_NOT_EXPORTED as a fact and give a concrete corrective check in human output. This fact does not require an invented probability or a proven function call.

The eager --call and --skip cases may have the same CONDITIONAL mismatch explanation and must both have overall INCONCLUSIVE and invocation UNKNOWN. The fixed hook case can have EXPECTED_BINDING_OBSERVED while still having those same overall/invocation statuses. The test harness, not the generic rule engine, establishes whether the controlled call and repair actually worked.

## 9. JSON schema v0.3

All keys in this example are required; empty collections and null retain their meaning. Additional fields require a documented, tested extension. The illustrative paths, PID and excerpts below are not measured project results.

```json
{
  "schema_version": "0.3",
  "status": "INCONCLUSIVE",
  "request": {
    "target_argv": ["./fixtures/app_large"],
    "resolved_executable": "/example/HookDoctor/fixtures/app_large",
    "hook_library": "/example/HookDoctor/fixtures/libhook_open.so",
    "expected_symbol": "open",
    "cwd": "/example/HookDoctor"
  },
  "facts": [
    {"id": "fact-001", "code": "TARGET_IMPORTS_SYMBOL", "status": "CONFIRMED", "message": "Target imports open64", "evidence_ids": ["ev-001"]},
    {"id": "fact-002", "code": "HOOK_EXPORTS_SYMBOL", "status": "CONFIRMED", "message": "Requested hook exports open", "evidence_ids": ["ev-002"]},
    {"id": "fact-003", "code": "SYMBOL_NOT_EXPORTED", "status": "CONFIRMED", "message": "Requested hook does not export open64", "evidence_ids": ["ev-002"]},
    {"id": "fact-004", "code": "BINDING_OBSERVED", "status": "CONFIRMED", "message": "Target open64 resolves to libc", "evidence_ids": ["ev-003"]}
  ],
  "diagnoses": [
    {
      "id": "SYMBOL_VARIANT_MISMATCH",
      "status": "CONDITIONAL",
      "message": "Target imports and binds open64; the requested hook exports open but not open64",
      "condition": "If this workload executes the observed open64 path, a hook exporting only open cannot intercept that open64 call.",
      "evidence_ids": ["ev-001", "ev-002", "ev-003"],
      "next_steps": ["Add a correct open64 wrapper and rerun the same target argv with the fixed library and --symbol open64"]
    }
  ],
  "observations": {
    "library_load": "UNKNOWN",
    "invocation": "UNKNOWN",
    "bindings": [
      {
        "pid": 1234,
        "caller_object": "/example/HookDoctor/fixtures/app_large",
        "symbol": "open64",
        "symbol_version": "GLIBC_2.2.5",
        "provider_object": "/lib/x86_64-linux-gnu/libc.so.6",
        "evidence_ids": ["ev-003"]
      }
    ]
  },
  "run": {
    "attempted": true,
    "target_exit_code": 0,
    "timed_out": false,
    "output_limited": false,
    "trace_complete": true,
    "stdout": "target: success\n",
    "stderr": "<bounded captured target and loader output>",
    "loader_environment": {
      "policy": "single_requested_preload",
      "LD_PRELOAD": "/example/HookDoctor/fixtures/libhook_open.so",
      "LD_DEBUG": "libs,bindings",
      "LD_LIBRARY_PATH": null,
      "LD_BIND_NOW": null,
      "removed": ["LD_AUDIT", "LD_DEBUG_OUTPUT", "LD_TRACE_LOADED_OBJECTS"],
      "overridden": ["LD_PRELOAD", "LD_DEBUG"]
    }
  },
  "evidence": [
    {"id": "ev-001", "source": "readelf", "summary": "Complete dynamic table includes undefined open64", "raw_excerpt": "<raw dynamic symbol row>"},
    {"id": "ev-002", "source": "nm", "summary": "Complete hook export table contains open and no open64", "raw_excerpt": "<raw export table excerpt; full collection checked>"},
    {"id": "ev-003", "source": "ld_debug", "summary": "Direct target PID binds target open64 to libc", "raw_excerpt": "<raw loader row with PID, caller, provider and symbol>"}
  ],
  "limitations": ["Loader binding does not establish function invocation or this workload's actual failure cause"],
  "errors": []
}
```

Rules for missing data and consistency:

- resolved_executable is null if target resolution failed. hook_library is the resolved absolute input path when possible, otherwise the provided value. Preserve original target_argv and cwd.
- facts require id, code, status, message and evidence_ids. diagnoses require id, status, message, condition, evidence_ids and next_steps. Every evidence ID must exist; do not invent placeholder evidence in real reports.
- Evidence source is validation, readelf, nm or ld_debug. Every item has id, source, summary and raw_excerpt. For validation, raw_excerpt may be an empty string and summary must state the actual check. Do not treat a command failure as a successful empty symbol table.
- Bindings require all fields shown; symbol_version is null if the recognized format supplies no version. Keep raw decorated names/version text in raw_excerpt. Exclude unattributed rows from qualifying bindings and preserve them as evidence/limitations when useful.
- If execution is skipped, run.attempted is false, target_exit_code is null, stdout/stderr are empty, trace_complete is false, library_load is NOT_RUN and bindings is empty. loader_environment is null when no target environment was prepared. For a launch failure after preparation, attempted is true and target_exit_code remains null.
- target_exit_code follows Python subprocess returncode: a nonnegative exit status, or a negative terminating signal on POSIX. timed_out and output_limited also flag a required collector hitting its bound, with the affected component named in errors.
- removed and overridden list the policy's controlled variable names, even if they were absent in the parent environment. Do not record inherited values of removed variables. The other loader_environment entries are the effective values used for the run.
- errors is a list of {"code": "...", "message": "..."}. Use stable codes INPUT_INVALID, UNSUPPORTED_ENVIRONMENT, COLLECTOR_FAILED, LAUNCH_FAILED, TIMEOUT or OUTPUT_LIMIT. status ERROR must have an error and exit code 3, 4 or 5. If several limits/failures occur during cleanup, retain the first primary failure as the CLI exit reason and record any others.
- Use UTF-8 JSON and decode non-UTF-8 subprocess bytes with replacement without crashing. Stable ordering applies to facts, diagnoses and evidence assignment for the same observations. Paths, PIDs and raw logs naturally vary; tests compare normalized semantics rather than pretending raw traces are byte-identical.
- Keep all captured output within the stated bounds. It may contain target-provided data; do not publish private application output or the full environment as part of a report.

## 10. Tests and reproducible demonstration

The project must work from its root using these commands without network access once the system tools are installed:

```bash
make -C fixtures all
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m hookdoctor --help
bash scripts/demo.sh
```

An optional virtual environment/editable install may expose hookdoc directly. Do not make a package download a prerequisite for the standard-library test path. scripts/demo.sh locates the project root, uses the module interface if needed and fails nonzero if a required expectation fails. HookDoctor exit code 0 alone is not proof that a fixture passed.

Required acceptance matrix:

| Case | Harness ground truth | Required generic check result |
| --- | --- | --- |
| app_normal, open-only hook, --symbol open | Target succeeds; open marker appears | EXPECTED_BINDING_OBSERVED fact; no mismatch diagnosis; invocation UNKNOWN |
| app_large, open-only hook, --symbol open | Same source compiled differently; target succeeds; neither marker appears | Conditional mismatch with ELF and attributed binding evidence; invocation UNKNOWN |
| Unchanged app_large, fixed hook, --symbol open64 | Same binary hash/argv; target succeeds; open64 marker appears | EXPECTED_BINDING_OBSERVED fact; no mismatch diagnosis; invocation UNKNOWN |
| app_conditional_now --call, open-only hook, --symbol open | Source/argument selects open path; target succeeds; no hook marker | Conditional mismatch; INCONCLUSIVE; invocation UNKNOWN |
| Same app_conditional_now --skip, open-only hook, --symbol open | Source/argument skips open; neither marker appears | Same conditional mismatch may appear; INCONCLUSIVE; invocation UNKNOWN; no claim of failure |
| Same app_conditional_now --skip, fixed hook, --symbol open64 | No open call and no hook marker although eager binding targets hook | EXPECTED_BINDING_OBSERVED fact; INCONCLUSIVE; invocation UNKNOWN |
| Same app_conditional_now --call, fixed hook, --symbol open64 | Call path runs; open64 marker appears | EXPECTED_BINDING_OBSERVED fact; INCONCLUSIVE; invocation UNKNOWN |
| Verified app_static, when supported | Genuine conventional static ELF | STATIC_EXECUTABLE fact; NOT_APPLICABLE; no run; code 0 |
| Valid no-export hook, --symbol open | Successful inspection proves export absent | SYMBOL_NOT_EXPORTED fact; INCONCLUSIVE after completed run; code 0 |
| Missing hook path or invalid ELF | Input validation fails | ERROR; no target execution; code 3; valid JSON if requested |

All completed supported dynamic rows have overall INCONCLUSIVE. The first three rows establish the demo's manual before/after result through harness evidence, while the generic tool reports only what its collection can establish. Repeat these three rows twice in the team's clean environment before accepting the fixture gate.

Additional focused tests must cover:

- Normal target-to-hook binding plus hook-to-libc forwarding in one trace, proving the latter is not misclassified as bypass.
- Lost/ambiguous caller attribution, unknown loader formats and truncated data: preserve facts, withhold the correlated mismatch and never infer invocation/absence.
- Versioned symbol parsing and dynamic-table absence versus collector failure; ET_EXEC dynamic targets and ET_DYN without PT_INTERP must not be classified as conventional static.
- A readable hook without its execute bit, paths with spaces in the target argv, an unchanged parent working directory/environment and shell metacharacters passed as literal arguments.
- A target that exits nonzero, a target that times out, one that floods output and one with a child holding a pipe open. Verify bounded completion, own-group cleanup, the correct error/exit code, captured partial evidence and parseable JSON. Use short deterministic C helpers or an explicit ELF interpreter path such as the resolved sys.executable with -c/script arguments. A Python script path alone is not a supported ELF target. For a target-flood integration test, choose a cap that allows ELF inspection to finish before target output reaches it; also test the bounded runner directly.
- Collector failure/timeout/output limits and skipped static support. Validate error fields and the distinction from missing exports.
- --json stdout parses as exactly one document with the required fields, allowed statuses and valid evidence references on success and reportable failure. Generic code must not depend on expected_cases.json or known marker text.

Record OS/architecture, Python, compiler, glibc and binutils versions; exact build/run commands; selected loader environment; ELF flags; exit statuses; relevant raw excerpts; binary hashes for the repaired workload; tests passed/failed/skipped; and current limitations. Store large raw logs under a documented evidence directory only if needed, with bounded capture. Do not claim all tests passed when a required gate is blocked.

## 11. Implementation sequence and first task

Start implementing the authorized project immediately in this order. Do not wait for remote repository setup to begin local work.

1. **Fixture gate, 2026-10-10 to 2026-10-11:** create the C sources, Makefile, expected_cases.json, tests/test_fixtures.py and docs/EVIDENCE.md. Verify imports/exports, normal/large/fixed runs, eager --call/--skip cases and the static-or-no-export secondary selection. Report the actual toolchain and observed limitations. This is the first reviewable implementation checkpoint.
2. **Model and inspector, 2026-10-12:** implement the section 9 model, __main__, help/version, input validation and bounded ELF collection. JSON must already represent failed or skipped collection honestly. Add focused inspector tests. Do not present a runtime diagnosis before the tracer exists.
3. **Tracer and correlation, 2026-10-13:** implement isolated environments, bounded collection, target PID/object attribution, pure diagnosis rules and terminal/JSON rendering. Add timeout/output/forwarding tests with this code. Preserve UNKNOWN for invocation.
4. **Acceptance and freeze, 2026-10-14:** run the full matrix, record evidence, complete the repeatable demo and freeze diagnosis scope. A failed gate is a documented limitation to resolve, not permission to fabricate success.
5. **Presentation, 2026-10-15:** replace proposed output with actual CLI results, explain the difference between observations and invocation, record a backup demo and rehearse within the 10-minute talk limit plus 5-minute Q&A.
6. **Midterm, 2026-10-16:** demonstrate the accepted behavior, disclose remaining limits and record professor/peer/mentor feedback for the final phase.

If the fixture does not reproduce, stop dependent diagnosis work and fix or document the environment first. If the runtime parser cannot establish attribution by the freeze, ship the honest static facts and UNKNOWN result, explicitly mark the correlated-diagnosis gate incomplete and reduce presentation claims. Do not use the last 48 hours for low-priority features.

At each checkpoint report what changed, exact verification commands/results and concrete remaining blockers. Continue routine authorized implementation without asking the user to reapprove the same work. Ask only for missing decisions that block dependent work, after completing useful independent work.

## 12. Final phase and evidence policy

After the midterm, select ONE real-world target during the following week and pin a reproducible release/commit and workload. Do not defer feasibility until November. Use an upstream open/open64 case such as libfaketime issue #362 as a lead to verify, not as evidence that the new CLI already works on that project. Record reproduction success or failure and choose the final target accordingly.

Late October: improve parser coverage and evaluate held-out fixtures. November: investigate one justified extension, such as versioned symbols or a dlopen scope issue, with its own counterexamples and evidence requirements. A mention of RTLD_DEEPBIND in source is not proof that a workload used that path or that it caused the observed issue. A before/after comparison command is optional and must remain separate from automatic code modification. December: evaluate diagnostic correctness, unresolved cases and manual workflow time, then prepare the public deliverables and 2026-12-11 demonstration when publishing is authorized. An Electron UI remains optional and consumes this JSON model.

Use these evidence labels in docs/EVIDENCE.md, docs/SOURCES.md and presentation claims:

- VERIFIED_BY_CODE: identify the inspected source, revision and relevant location.
- REPRODUCED_LOCAL: record the exact executed workload, toolchain and raw result.
- DOCUMENTED_UPSTREAM: link official documentation or an upstream issue and state what it actually supports.
- HYPOTHESIS: make the untested condition explicit and specify the next check.

Reference sources:

- glibc loader behavior: https://man7.org/linux/man-pages/man8/ld.so.8.html
- glibc feature-test macros: https://www.gnu.org/software/libc/manual/html_node/Feature-Test-Macros.html
- GNU readelf: https://sourceware.org/binutils/docs/binutils/readelf.html
- libfaketime upstream open/open64 issue: https://github.com/wolfcw/libfaketime/issues/362
- libfaketime: https://github.com/wolfcw/libfaketime
- heaptrack: https://github.com/KDE/heaptrack
- libtree: https://github.com/haampie/libtree
- LD_PRELOAD_MCP: https://github.com/michigan-public-tech-org/LD_PRELOAD_MCP
- BoB14 DynamicAnalysis: https://github.com/BOB14th-project/DynamicAnalysis
- PyCryptodome raw API source: https://github.com/Legrandin/pycryptodome/blob/master/lib/Crypto/Util/_raw_api.py
- Course introduction, dates and evaluation: https://drive.google.com/file/d/10NDfpn8AwVR5YuhvfF-OLM0hu_kfSfGy/view

Never mark a CLI feature as implemented merely because the fixture, another tool or an earlier experiment produced the desired output. Acceptance requires evidence from the newly written HookDoctor implementation under this contract.
