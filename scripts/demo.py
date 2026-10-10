"""Controlled, reproducible acceptance demo. Never imported by production modules."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

from hookdoctor.process import run_bounded

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from support import assert_schema, codes  # noqa: E402

ENV = {k: v for k, v in os.environ.items() if not k.startswith("LD_")}
ENV.update(LC_ALL="C", PYTHONPATH=str(ROOT / "src"))
OUT = Path(os.environ.get("HOOKDOCTOR_DEMO_DIR", ROOT / "docs/evidence/demo"))
COMMANDS = []


def run(argv, *, timeout=15):
    result = run_bounded(argv, env=ENV, cwd=ROOT, timeout=timeout, max_bytes=5242880)
    COMMANDS.append({"argv": list(map(str, argv)), "cwd": str(ROOT),
                     "environment": {"remove_inherited": "LD_*", "LC_ALL": "C", "PYTHONPATH": str(ROOT / "src")},
                     "exit_code": result.returncode, "timed_out": result.timed_out,
                     "output_limited": result.output_limited,
                     "stdout": result.stdout.decode("utf-8", "replace"),
                     "stderr": result.stderr.decode("utf-8", "replace")})
    if not result.complete:
        raise RuntimeError(f"Demo command bound: {argv}")
    return result


def cli(name, argv, lib, symbol="open", expected_code=0):
    result = run([sys.executable, "-m", "hookdoctor", "check", "--lib", str(lib),
                  "--symbol", symbol, "--json", "--", *argv])
    if result.returncode != expected_code:
        raise AssertionError(f"{name}: CLI code {result.returncode}; {result.stdout[:1500]!r} {result.stderr[:500]!r}")
    report = json.loads(result.stdout)
    assert_schema(report)
    (OUT / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("ENVIRONMENT: Linux x86-64 required; use scripts/dev.sh")
    require(run(["make", "-C", "fixtures", "all"]).returncode == 0, "fixture build failed")
    cases = json.loads((ROOT / "fixtures/expected_cases.json").read_text())
    digest = lambda: hashlib.sha256((ROOT / "fixtures/app_large").read_bytes()).hexdigest()
    before = digest()
    rows = []
    for case in cases:
        if case["name"] == "fixed":
            require(run(["cc", "-shared", "-fPIC", "-DWITH_OPEN64", "fixtures/hook.c", "-o", "fixtures/libhook_fixed.so", "-ldl"]).returncode == 0, "manual fixed-hook build failed")
            require(case["argv"] == cases[1]["argv"], "workload argv changed")
            require(digest() == before, "workload binary changed")
        report = cli(case["name"], case["argv"], ROOT / "fixtures" / case["lib"], case["symbol"])
        require(report["status"] == "INCONCLUSIVE", f"{case['name']}: status")
        require(report["run"]["target_exit_code"] == 0, f"{case['name']}: target exit")
        require(report["run"]["stdout"] == case["stdout"], f"{case['name']}: harness completion")
        require(report["run"]["trace_complete"], f"{case['name']}: incomplete trace")
        require(bool(report["diagnoses"]) == case["mismatch"], f"{case['name']}: mismatch rule")
        if case["fact"]:
            require(case["fact"] in codes(report), f"{case['name']}: expected fact missing")
        for marker in ("open", "open64"):
            require((f"[HOOK] {marker} intercepted" in report["run"]["stderr"]) == (case["marker"] == marker), f"{case['name']}: harness marker")
        rows.append({"name": case["name"], "status": report["status"], "marker": case["marker"],
                     "invocation": report["observations"]["invocation"], "diagnoses": [d["id"] for d in report["diagnoses"]], "facts": sorted(codes(report))})
        print(f"PASS {case['name']}: {report['status']}; harness marker={case['marker']}; CLI invocation=UNKNOWN", flush=True)
    static_build = run(["make", "-C", "fixtures", "static"])
    if static_build.returncode == 0:
        report = cli("static", ["./fixtures/app_static"], ROOT / "fixtures/libhook_open.so")
        require(report["status"] == "NOT_APPLICABLE" and "STATIC_EXECUTABLE" in codes(report) and not report["run"]["attempted"], "static must be inspected and skipped")
        secondary = "verified conventional static ELF (compiler support available); no-export case also passed"
        print("PASS static: NOT_APPLICABLE; target not run", flush=True)
    else:
        secondary = "no-export hook selected; static SKIPPED because compilation failed (see commands.json)"
        print("SKIP static: compilation unavailable; no-export hook satisfies secondary case", flush=True)
    missing = cli("missing-library", ["./fixtures/app_normal"], ROOT / "fixtures/absent-library.so", expected_code=3)
    require(missing["status"] == "ERROR" and not missing["run"]["attempted"], "missing library must fail before target execution")
    after = digest()
    require(before == after, "app_large hash changed")
    elapsed = time.monotonic() - started
    require(elapsed < 120, "demo exceeded two-minute acceptance gate")
    summary = {"result": "PASS", "elapsed_seconds": round(elapsed, 3), "secondary": secondary,
               "app_large_sha256_before": before, "app_large_sha256_after": after,
               "same_workload_argv": cases[1]["argv"], "cases": rows}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS unchanged app_large SHA-256: {after}")
    print(f"PASS demo completed in {elapsed:.3f}s. {secondary}")


if __name__ == "__main__":
    try:
        main()
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "commands.json").write_text(json.dumps(COMMANDS, ensure_ascii=False, indent=2) + "\n")
