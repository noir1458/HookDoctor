# HookDoctor implementation evidence

Date: **2026-10-10 (Asia/Seoul)**. Contract: AGENTS.md v0.3. CLI: **0.3.0**.
Scope: local implementation and verification, with source on an Apple Silicon Mac
and acceptance execution inside a Docker **linux/amd64** container. The original
contract is unchanged. These results concern the newly implemented CLI, not the
earlier reference experiment. Remote publication was not part of that initial
implementation run; the authorized commit/reproduction checkpoint is recorded below.

## Result and records

**REPRODUCED_LOCAL:** fixture gate passed before dependent MVP implementation.
The latest saved fixture check passed **3 tests in 3.347 s**. The saved full suite passed
**40 tests in 20.358 s**, **0 failed, 0 skipped**. The demo passed in **3.321 s**,
including fixture make, manual fixed-hook build and all CLI runs, below 120 s.
The demo also has an outer 115 s execution bound. Initial image download and
package installation are setup steps, excluded from demo timing.

- [Final unittest output](evidence/acceptance/tests.txt)
- [Fixture gate output](evidence/fixture-gate/tests.txt)
- [Raw fixture commands, metadata and loader traces](evidence/fixture-gate/fixture-records.json)
- [Demo output](evidence/acceptance/demo.txt), [summary](evidence/demo/summary.json)
- [Exact demo commands and outputs](evidence/demo/commands.json)
- [Source snapshot hashes](evidence/source-sha256.json): hashes of the frozen implementation/configuration files.

## Environment and resolved failures

| Component | Actual observation |
| --- | --- |
| Development host | Darwin arm64 (Apple Silicon) |
| Docker client / server | 29.8.0 / 29.8.0; desktop-linux context |
| Docker VM | linux/aarch64, distinct from container architecture |
| Image OS / architecture | linux/amd64, checked before execution |
| Container release | Ubuntu 24.04.5 LTS, VERSION_ID=24.04 |
| Container uname | Linux 7.0.12-linuxkit, x86_64 |
| Python | 3.12.3 |
| Compiler | cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 |
| glibc | 2.39; installed libc package 2.39-0ubuntu8.9 |
| GNU readelf / nm | GNU Binutils for Ubuntu 2.42 |
| Test/demo identity | uid=501, gid=20; no root or privileged container |
| Runtime network | disabled by --network none |

Base image resolved during build:
`ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55`.
Development image ID:
`sha256:57bed9a121706365a8728d780217633bdb713a04870df7df5d000d9d30c5fad6`.
Image name: `hookdoctor-dev:ubuntu24.04-amd64`. The Ubuntu tag and apt repositories
may change on future builds; preserve this image or compare versions and re-run
the gate. This is not a claim of byte-identical future package rebuilds.

The contract reference used Ubuntu 24.04.3; the current tag supplied 24.04.5. The
actual 24.04/glibc/x86-64 environment reproduced the required behavior. Native
x86-64 hardware was **not tested**. Apple Silicon amd64 execution uses Docker's
translation support; its particular Rosetta/QEMU backend was not separately identified.

Initial failures were distinguished and resolved:

1. **Environment availability:** Docker was installed but its daemon socket did
   not exist. Starting Docker Desktop restored it. A sandboxed Desktop status
   probe could not write its own host log; successful engine/container queries
   established availability separately.
2. **Host script compatibility:** macOS Bash 3.2 rejected an empty-array expansion
   under `set -u`. The launcher was changed to prepend arguments without an empty
   array. All subsequent container invocations succeeded.
3. **Implementation bug:** an initial parser smoke run sliced a regex Match
   instead of calling `groups()`. It was fixed before acceptance; real symbol
   parsing and focused parser tests now pass. This was not a fixture/emulation failure.

No remaining environment blocker or required skipped acceptance check was observed.

## Reproduction commands and fixture evidence

On the Mac, from this project root:

```bash
bash scripts/dev.sh build
bash scripts/dev.sh bash scripts/verify-fixtures.sh
bash scripts/dev.sh bash scripts/verify.sh
```

**VERIFIED_BY_CODE:** Dockerfile/dev.sh build and run with `--platform linux/amd64`,
mount only this project at `/workspace`, use the host UID/GID and disable runtime
networking. System build-essential, binutils and Python are installed; no pip
download is required. The source and generated ELF files remain in the Mac project.

The standard contract commands were exercised inside the container:

```bash
make -C fixtures all
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m hookdoctor --help
PYTHONPATH=src python3 -m hookdoctor --version
bash scripts/demo.sh
```

The fixture gate additionally uses `make -B -C fixtures all` so each saved run
includes actual compiler commands even when artifacts already exist. The recipes
are exactly the contract flags. All six dynamic artifacts receive header,
program-header and dynamic-section inspection; dynamic imports and nm exports are
checked separately. The separate static build/inspection succeeded.

Both normal and large targets use `fixtures/app.c`. Observed imports:
`open@GLIBC_2.2.5` and `open64@GLIBC_2.2.5`, respectively. The single conditional
binary imports `open64@GLIBC_2.2.5` and has `(FLAGS) BIND_NOW` and `(FLAGS_1) Flags:
NOW PIE`. Compiler defaults also made normal/large eager in this environment.
Hook export sets: open-only `{open}`, fixed `{open, open64}`, no-export
`{hookdoctor_unrelated}`.

The fixture harness executes the first three cases **twice**, then eager and
no-export cases. It removes inherited `LD_*`, sets `LC_ALL=C`, uses an absolute
`LD_PRELOAD` and `LD_DEBUG=libs,bindings`. Exact argv, selected environment, direct
PID, bounded raw stdout/stderr, exit status and ELF output are in fixture-records.json.
The generic CLI separately preserves LD_LIBRARY_PATH/LD_BIND_NOW; both were null
in this clean demo. It removes LD_AUDIT, LD_DEBUG_OUTPUT, LD_TRACE_LOADED_OBJECTS
and overrides LD_PRELOAD/LD_DEBUG, recording the policy without the full environment.

## New CLI acceptance matrix

All completed dynamic cases below returned CLI code **0**, overall
**INCONCLUSIVE**, invocation **UNKNOWN**, trace_complete **true**, target exit **0**.
Markers and deterministic completion text are harness observations, not generic rule inputs.

| Target / hook / symbol | Harness observation | Generic result |
| --- | --- | --- |
| app_normal / open-only / open | success, open marker | EXPECTED_BINDING_OBSERVED, no mismatch |
| app_large / open-only / open | success, neither marker | CONDITIONAL SYMBOL_VARIANT_MISMATCH |
| same app_large / fixed / open64 | success, open64 marker | EXPECTED_BINDING_OBSERVED, no mismatch |
| conditional --call / open-only / open | target: called, neither marker | CONDITIONAL mismatch |
| same conditional --skip / open-only / open | target: skipped, neither marker | same CONDITIONAL mismatch |
| same conditional --skip / fixed / open64 | target: skipped, neither marker | EXPECTED_BINDING_OBSERVED |
| same conditional --call / fixed / open64 | target: called, open64 marker | EXPECTED_BINDING_OBSERVED |
| app_normal / no-export / open | success, neither marker | SYMBOL_NOT_EXPORTED fact |
| verified app_static / open-only / open | no target execution | STATIC_EXECUTABLE, NOT_APPLICABLE, code 0 |
| app_normal / missing library / open | no target execution | LIBRARY_NOT_FOUND, ERROR, code 3 |

Reports: [large](evidence/demo/large.json), [fixed](evidence/demo/fixed.json),
[eager skip](evidence/demo/eager_skip.json),
[eager skip, fixed hook](evidence/demo/eager_skip_fixed.json),
[static](evidence/demo/static.json), [missing input](evidence/demo/missing-library.json).

Secondary selection: **verified conventional static ELF**, because compilation
was available. readelf established ET_EXEC, no PT_INTERP, no PT_DYNAMIC and no
DT_NEEDED. HookDoctor did not launch it. The no-export fallback was also executed.
A focused test simulates static compiler failure and verifies a reasoned SKIP
without inspecting/fabricating a substitute. The real static check was not skipped.

## Repair and interpretation

Manual repair command executed by the demo harness, not HookDoctor:

```bash
cc -shared -fPIC -DWITH_OPEN64 fixtures/hook.c -o fixtures/libhook_fixed.so -ldl
```

Unchanged workload argv: `["./fixtures/app_large"]`. SHA-256 before and after:
`e4d0f289e4634ec4aecf3e62082be1834fdeaae2cbcdcdc2c63d3208a9a6714d`.
The expected diagnostic symbol changes from open to open64, as required.

The eager --skip reports contain a target-origin open64 binding to libc or the
fixed hook even though the controlled source/argv selects the no-open branch and
emits no hook marker. Binding is relocation evidence, not wrapper-entry evidence.
The raw versioned binding rows and PIDs remain in each report's evidence/run fields.

**HYPOTHESIS / emitted condition:** "If this workload executes the observed open64
path, a hook exporting only open cannot intercept that open64 call."
The only primary diagnosis family is SYMBOL_VARIANT_MISMATCH. Compiler flags are
known harness inputs, never generic inferred facts. A provider qualifies as libc
only if its canonical identity matches libc.so.6 mapped in the confirmed glibc
analyzer process; similar filenames alone are insufficient.

## Code and focused validation

**VERIFIED_BY_CODE**, using evidence/source-sha256.json as the source revision:

- `models.py`: schema v0.3, stable evidence IDs and resolved references.
- `inspector.py`: complete bounded GNU tables, versions/visibility, clean helper
  environment, input/architecture/loader checks and conservative static classification.
- `process.py`: incremental combined stdout/stderr cap; deadline also covers pipe
  draining; dedicated process groups; TERM/0.5 s grace/KILL and finally cleanup.
- `tracer.py`: one target run; loader policy; direct PID/canonical object attribution;
  partial rows, other-object forwarding and child PIDs do not support the mismatch.
- `diagnose.py`: pure rules, conditional explanation and UNKNOWN invocation.
- `cli.py`/`reporting.py`: strict options, preserved argv without shell execution,
  codes 0/2/3/4/5, one JSON document per parsed request, and separate terminal facts,
  conditional explanations, uncertainty and next check. `pyproject.toml` defines hookdoc.
- Fixtures/tests/demo alone use expected_cases.json and marker ground truth.

**REPRODUCED_LOCAL:** tests cover real forwarding, lost/ambiguous attribution,
child PIDs, unknown formats, truncated tables/rows, versions, dynamic ET_EXEC and
static PIE, no-execute-bit hook, target paths with spaces, literal shell syntax,
unchanged parent cwd/environment, nonzero and signalled targets, invalid UTF-8,
target timeout/output flood/child-held pipe, TERM-ignoring target, caught interrupt,
unrelated process survival, real collector failure/5 s timeout/output limit,
static-unavailable fallback behavior, strict parsing, JSON fields/statuses and
evidence references. Some focused tests use synthetic/injected observations; the
acceptance matrix and process bounds use real subprocesses. All 40 passed.

## Limits and unverified items

- Native Linux x86-64 hardware was not tested. This is a Mac-hosted amd64 container result.
- Generic function entry and the workload's actual failure cause remain UNKNOWN.
  Controlled fixture evidence does not extend generic observability.
- Static PIE, other architectures/loaders, script/PATH launchers, child diagnosis
  and unusual scopes are outside the MVP. Unknown output/custom libc identities
  may retain facts without a correlated explanation. Version text is preserved,
  but base-name comparison does not establish version compatibility.
- Secure-execution checks include set-ID/file capabilities but are incomplete.
  stderr can be imitated by targets. This is a debugging tool, not a malware sandbox;
  processes deliberately escaping its owned group are not containment targets.
- Raw excerpts are at most 4096 UTF-8 bytes each and 65536 total; each subprocess's
  captured bytes have the separate configured combined stdout/stderr cap. Complete
  captured target streams are in run.stdout/run.stderr within that cap.
- The optional installed hookdoc entry point is declared but was not package-installed
  here; all acceptance uses the required offline standard-library module interface.
- GUI, server, deployment, upstream real-world evaluation, human/course approval
  and presentation materials are outside this run. The two upstream manual fetch
  failures noted in SOURCES.md do not replace the recorded local evidence.

## Midterm scope freeze and presentation claims

The v0.3 implementation scope is frozen: Linux x86-64/glibc CLI, one exact symbol,
ELF/loader correlation, one conditional open/open64 mismatch family, bounded
execution, static/no-export handling and schema v0.3 output. This checkpoint adds
version control and reproducibility documentation, not new diagnosis behavior.

Supported presentation claims:

- Implemented a CLI that correlates ELF imports/exports with direct-target loader binding.
- Reproduced controlled interception, symbol mismatch and manual repair while retaining the same target binary/argv.
- Demonstrated eager no-call counterexamples and retained UNKNOWN for generic invocation.
- Passed the current 40-test suite and the sub-two-minute controlled demo in the recorded Docker environment.

These are local self-validation results. They are not an independent audit,
universal interception, a measured detection accuracy of 100%, or validation on
arbitrary real-world projects. Native x86-64 Linux cross-validation remains **NOT
RUN** until executed on actual Intel/AMD hardware. Course acceptance and the
presentation itself remain separate milestones.
