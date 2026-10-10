import argparse
import math
import os
from pathlib import Path
import sys

from . import __version__
from .diagnose import INVOCATION_LIMIT, runtime_facts, static_facts
from .inspector import Inspector
from .models import AnalysisError, Report, Request
from .reporting import render_json, render_terminal
from .tracer import trace


def positive_timeout(value):
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be finite and positive") from exc
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return result


def positive_bytes(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max-output-bytes must be a positive integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("max-output-bytes must be a positive integer")
    return result


def symbol_name(value):
    if not value or "@" in value or any(c.isspace() or ord(c) < 32 for c in value):
        raise argparse.ArgumentTypeError("symbol must be one exact unversioned dynamic name without whitespace")
    return value


def parser():
    result = argparse.ArgumentParser(prog="hookdoc", description="Correlate ELF symbols and glibc loader binding; invocation remains UNKNOWN.")
    result.add_argument("--version", action="version", version=f"hookdoc {__version__}")
    sub = result.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="execute one bounded target workload", usage="hookdoc check --lib LIB --symbol SYMBOL [options] -- ./target [args ...]")
    check.add_argument("--lib", required=True)
    check.add_argument("--symbol", required=True, type=symbol_name)
    check.add_argument("--json", action="store_true")
    check.add_argument("--timeout", type=positive_timeout, default=10.0)
    check.add_argument("--max-output-bytes", type=positive_bytes, default=5242880)
    return result


def analyze(options, target_argv):
    # Resolve the hook independently so error reports retain the absolute input path.
    try:
        hook_path = str(Path(options.lib).resolve())
    except (OSError, ValueError, RuntimeError):
        hook_path = options.lib
    report = Report(Request(list(target_argv), None, hook_path, options.symbol, os.getcwd()))
    report.limitations.extend([INVOCATION_LIMIT,
        "Loader stderr is not authenticated telemetry; target output can share or imitate it",
        "Secure-execution detection is incomplete; child processes and unusual loader scopes are outside this MVP"])
    code = 0
    try:
        inspector = Inspector(report, options.max_output_bytes)
        inspector.paths()
        inspector.platform()
        target = inspector.inspect(report.request.resolved_executable)
        hook = inspector.inspect(report.request.hook_library, hook=True)
        if (target.elf_class, target.machine) != (hook.elf_class, hook.machine):
            raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "Target/hook ELF class and machine are incompatible")
        if target.static:
            report.status = "NOT_APPLICABLE"
            report.add_fact("STATIC_EXECUTABLE", "Conventional static ET_EXEC with no PT_INTERP, PT_DYNAMIC or DT_NEEDED; target execution skipped", [target.header_evidence, target.symbol_evidence])
        else:
            static_facts(report, target, hook)
            trace_facts, error = trace(report, inspector.identities, timeout=options.timeout, max_bytes=options.max_output_bytes)
            report.status = "ERROR" if error else "INCONCLUSIVE"
            runtime_facts(report, target, hook, trace_facts)
            if error:
                raise error
    except AnalysisError as exc:
        report.status = "ERROR"
        report.run.trace_complete = False
        report.errors.append(dict(code=exc.code, message=str(exc)))
        code = exc.exit_code
    except (OSError, ValueError, KeyboardInterrupt) as exc:
        report.status = "ERROR"
        report.run.trace_complete = False
        report.errors.append(dict(code="COLLECTOR_FAILED", message=f"Analysis interrupted or unavailable: {type(exc).__name__}: {exc}"))
        code = 3
    return report, code


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    argparser = parser()
    separator = argv.index("--") if "--" in argv else len(argv)
    options = argparser.parse_args(argv[:separator])
    target = argv[separator + 1:]
    if not target or not target[0]:
        argparser.error("check requires -- followed by an explicit executable path and optional arguments")
    report, code = analyze(options, target)
    print(render_json(report) if options.json else render_terminal(report))
    return code
