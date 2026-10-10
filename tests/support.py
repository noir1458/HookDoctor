import json
import os
from pathlib import Path
import platform
import sys
import unittest

from hookdoctor.process import run_bounded

ROOT = Path(__file__).resolve().parents[1]
ENV = {k: v for k, v in os.environ.items() if not k.startswith("LD_")}
ENV.update(LC_ALL="C", PYTHONPATH=str(ROOT / "src"))
LINUX = platform.system() == "Linux" and platform.machine() == "x86_64"
linux_only = unittest.skipUnless(LINUX, "Linux x86-64 integration: use scripts/dev.sh")


def invoke(*args, env=None, cwd=None):
    result = run_bounded([sys.executable, "-m", "hookdoctor", *args], env=ENV if env is None else env,
                         cwd=cwd or ROOT, timeout=20, max_bytes=16777216)
    if not result.complete:
        raise AssertionError("test harness CLI bound exceeded")
    return result


def check(argv, *, lib=None, symbol="open", options=(), env=None, cwd=None):
    result = invoke("check", "--lib", str(lib or ROOT / "fixtures/libhook_open.so"),
                    "--symbol", symbol, "--json", *options, "--", *map(str, argv), env=env, cwd=cwd)
    try:
        report = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise AssertionError(f"CLI did not emit exactly one JSON document: {result.stdout[:1000]!r} {result.stderr[:1000]!r}") from exc
    assert_schema(report)
    return result.returncode, report


def assert_schema(report):
    expected = {"schema_version", "status", "request", "facts", "diagnoses", "observations", "run", "evidence", "limitations", "errors"}
    assert set(report) == expected, set(report)
    assert report["schema_version"] == "0.3"
    assert report["status"] in {"INCONCLUSIVE", "NOT_APPLICABLE", "ERROR"}
    assert set(report["request"]) == {"target_argv", "resolved_executable", "hook_library", "expected_symbol", "cwd"}
    assert set(report["observations"]) == {"library_load", "invocation", "bindings"}
    assert report["observations"]["invocation"] == "UNKNOWN"
    assert report["observations"]["library_load"] in {"OBSERVED", "UNKNOWN", "NOT_RUN"}
    assert set(report["run"]) == {"attempted", "target_exit_code", "timed_out", "output_limited", "trace_complete", "stdout", "stderr", "loader_environment"}
    ids = {item["id"] for item in report["evidence"]}
    assert len(ids) == len(report["evidence"])
    for item in report["evidence"]:
        assert set(item) == {"id", "source", "summary", "raw_excerpt"}
        assert item["source"] in {"validation", "readelf", "nm", "ld_debug"}
    assert sum(len(e["raw_excerpt"].encode()) for e in report["evidence"]) <= 65536
    for key, fields, status in (("facts", {"id", "code", "status", "message", "evidence_ids"}, "CONFIRMED"),
                                ("diagnoses", {"id", "status", "message", "condition", "evidence_ids", "next_steps"}, "CONDITIONAL")):
        for item in report[key]:
            assert set(item) == fields
            assert item["status"] == status
            assert item["evidence_ids"] and set(item["evidence_ids"]) <= ids
    for item in report["observations"]["bindings"]:
        assert set(item) == {"pid", "caller_object", "symbol", "symbol_version", "provider_object", "evidence_ids"}
        assert set(item["evidence_ids"]) <= ids
    if report["status"] == "ERROR":
        assert report["errors"] and not report["run"]["trace_complete"]
    if not report["run"]["attempted"]:
        assert report["run"]["target_exit_code"] is None
        assert report["run"]["stdout"] == report["run"]["stderr"] == ""
        assert report["observations"]["library_load"] == "NOT_RUN"
        assert report["observations"]["bindings"] == []


def codes(report):
    return {fact["code"] for fact in report["facts"]}
