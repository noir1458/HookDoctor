"""One bounded target run and conservative direct-target loader attribution."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from .inspector import same_object
from .models import AnalysisError
from .process import run_bounded

BINDING = re.compile(r"^\s*(\d+):\s+binding file (.+?) \[0\] to (.+?) \[0\]: normal symbol [`']([^'\s]+)'(?: \[([^\]]+)\])?\s*$")
INIT = re.compile(r"^\s*(\d+):\s+calling init:\s+(.+?)\s*$")


@dataclass
class TraceFacts:
    loaded: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    libc_variant: list[str] = field(default_factory=list)


def target_environment(hook, parent=None):
    env = dict(os.environ if parent is None else parent)
    removed = ["LD_AUDIT", "LD_DEBUG_OUTPUT", "LD_TRACE_LOADED_OBJECTS"]
    for name in removed:
        env.pop(name, None)
    env.update(LD_PRELOAD=hook, LD_DEBUG="libs,bindings")
    policy = {"policy": "single_requested_preload", "LD_PRELOAD": hook,
              "LD_DEBUG": "libs,bindings", "LD_LIBRARY_PATH": env.get("LD_LIBRARY_PATH"),
              "LD_BIND_NOW": env.get("LD_BIND_NOW"), "removed": removed,
              "overridden": ["LD_PRELOAD", "LD_DEBUG"]}
    return env, policy


def resolve_logged(value, cwd):
    # A bare soname cannot establish which object the loader meant.
    if "/" not in value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = Path(cwd) / path
    try:
        resolved = path.resolve(strict=True)
        return str(resolved) if resolved.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


def parse_trace(report, pid, identities):
    facts = TraceFacts()
    request = report.request
    ignored = []
    seen = set()
    for raw_line in report.run.stderr.splitlines(keepends=True):
        if not raw_line.endswith("\n"):
            continue  # A truncated final row cannot establish a binding.
        line = raw_line.rstrip("\r\n")
        init = INIT.fullmatch(line)
        if init and int(init[1]) == pid:
            obj = resolve_logged(init[2], request.cwd)
            if same_object(obj, request.hook_library):
                ev = report.add_evidence("ld_debug", "Direct target PID initialized the requested hook object", line)
                facts.loaded.append(ev)
        match = BINDING.fullmatch(line)
        if not match:
            if "binding file" in line and len(ignored) < 5:
                ignored.append(line)
            continue
        event_pid, caller_raw, provider_raw, symbol, version = match.groups()
        caller = resolve_logged(caller_raw, request.cwd)
        provider = resolve_logged(provider_raw, request.cwd)
        if int(event_pid) != pid or not same_object(caller, request.resolved_executable) or not provider:
            if len(ignored) < 5:
                ignored.append(line)
            continue
        key = (caller, provider, symbol, version)
        if key in seen:
            continue
        seen.add(key)
        ev = report.add_evidence("ld_debug", f"Direct target PID {pid}: {symbol} version={version!r} binds to {provider}", line)
        report.observations.bindings.append(dict(pid=pid, caller_object=caller, symbol=symbol,
            symbol_version=version, provider_object=provider, evidence_ids=[ev]))
        if same_object(provider, request.hook_library):
            facts.loaded.append(ev)
            if symbol == request.expected_symbol:
                facts.expected.append(ev)
        elif symbol == "open64" and any(same_object(provider, libc) for libc in identities["libc"]):
            identity_ev = report.add_evidence("validation", f"Binding provider {provider} is the same canonical object as libc.so.6 mapped into the glibc analyzer process")
            facts.libc_variant.extend([ev, identity_ev])
    if ignored:
        report.add_evidence("ld_debug", "Excluded rows: other PID/object, unresolved identity, scope or unrecognized format; no main diagnosis attribution", "\n".join(ignored))
    report.observations.library_load = "OBSERVED" if facts.loaded else "UNKNOWN"
    if not report.observations.bindings:
        report.limitations.append("No attributable direct-target binding observed; this does not establish absence of binding or invocation")
    return facts


def trace(report, identities, *, timeout, max_bytes):
    env, policy = target_environment(report.request.hook_library)
    report.run.loader_environment = policy
    report.run.attempted = True
    report.observations.library_load = "UNKNOWN"
    try:
        result = run_bounded(report.request.target_argv, env=env, cwd=report.request.cwd,
                             timeout=timeout, max_bytes=max_bytes)
    except (OSError, ValueError) as exc:
        raise AnalysisError("LAUNCH_FAILED", f"Target launch failed: {exc}") from exc
    report.run.target_exit_code = result.returncode
    report.run.stdout = result.stdout.decode("utf-8", "replace")
    report.run.stderr = result.stderr.decode("utf-8", "replace")
    report.run.timed_out = result.timed_out
    report.run.output_limited = result.output_limited
    report.run.trace_complete = result.complete
    facts = parse_trace(report, result.pid, identities)
    # Return partial positive observations too, but no conditional diagnosis on an error.
    error = None
    if result.timed_out:
        error = AnalysisError("TIMEOUT", f"Target/stream drain exceeded {timeout:g} seconds", 4)
    elif result.output_limited:
        error = AnalysisError("OUTPUT_LIMIT", f"Target exceeded {max_bytes} captured stdout+stderr bytes", 5)
    return facts, error
