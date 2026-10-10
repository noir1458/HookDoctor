"""Controlled workload ground truth. These expectations never enter the CLI."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import unittest

from hookdoctor.process import run_bounded

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "fixtures/expected_cases.json").read_text())
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("LD_")}
CLEAN_ENV["LC_ALL"] = "C"
RECORDS = []


def collect(argv, env=None):
    result = run_bounded(argv, cwd=ROOT, env=env or CLEAN_ENV)
    record = {"argv": list(map(str, argv)), "cwd": str(ROOT),
              "environment": {"remove_inherited": "LD_*", "LC_ALL": "C"},
              "pid": result.pid, "exit_code": result.returncode,
              "timed_out": result.timed_out, "output_limited": result.output_limited,
              "stdout": result.stdout.decode("utf-8", "replace"),
              "stderr": result.stderr.decode("utf-8", "replace")}
    if env:
        record["environment"].update({k: v for k, v in env.items() if k.startswith("LD_")})
    RECORDS.append(record)
    if not result.complete:
        raise AssertionError(f"ENVIRONMENT/COLLECTION bound: {argv}")
    return record


def checked(argv):
    record = collect(argv)
    if record["exit_code"]:
        raise AssertionError(f"BUILD/COLLECTOR: {argv}: {record['stderr']}")
    return record["stdout"]


def symbols(path):
    text = checked(["readelf", "--wide", "--dyn-syms", str(path)])
    rows = [line.split() for line in text.splitlines() if re.match(r"\s*\d+:", line)]
    return {row[7].split("@")[0] for row in rows if len(row) >= 8 and row[6] == "UND"}


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() == "x86_64",
                     "requires Linux x86-64; use scripts/dev.sh")
class FixtureGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RECORDS.clear()
        # Preserve actual compiler commands even when artifacts already exist.
        checked(["make", "-B", "-C", "fixtures", "all"])
        for argv in (["uname", "-a"], ["python3", "--version"], ["cc", "--version"],
                     ["getconf", "GNU_LIBC_VERSION"], ["readelf", "--version"],
                     ["nm", "--version"], ["cat", "/etc/os-release"], ["id"]):
            checked(argv)
        cls.metadata = {}
        for name in ("app_normal", "app_large", "app_conditional_now", "libhook_open.so",
                     "libhook_fixed.so", "libhook_no_export.so"):
            cls.metadata[name] = checked(["readelf", "--wide", "-h", "-l", "-d",
                                          f"fixtures/{name}"])
        cls.before = hashlib.sha256((ROOT / "fixtures/app_large").read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        after = hashlib.sha256((ROOT / "fixtures/app_large").read_bytes()).hexdigest()
        directory = os.environ.get("HOOKDOCTOR_EVIDENCE_DIR")
        if directory:
            destination = Path(directory)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "fixture-records.json").write_text(json.dumps({
                "app_large_sha256_before": cls.before, "app_large_sha256_after": after,
                "commands": RECORDS}, indent=2) + "\n")
        if cls.before != after:
            raise AssertionError("Workload binary changed during manual hook repair")

    def test_dynamic_elf_and_symbols(self):
        self.assertIn("open", symbols("fixtures/app_normal"))
        self.assertNotIn("open64", symbols("fixtures/app_normal"))
        self.assertIn("open64", symbols("fixtures/app_large"))
        self.assertNotIn("open", symbols("fixtures/app_large"))
        self.assertIn("open64", symbols("fixtures/app_conditional_now"))
        for name, metadata in self.metadata.items():
            with self.subTest(name=name):
                self.assertIn("ELF64", metadata)
                self.assertIn("Advanced Micro Devices X86-64", metadata)
                self.assertRegex(metadata, r"(?m)^\s*DYNAMIC\s")
        self.assertRegex(self.metadata["app_conditional_now"], r"BIND_NOW|Flags:.*NOW")
        for lib, wanted in (("open", {"open"}), ("fixed", {"open", "open64"}),
                            ("no_export", set())):
            text = checked(["nm", "-D", "--defined-only", f"fixtures/libhook_{lib}.so"])
            exported = {line.split()[-1].split("@")[0] for line in text.splitlines() if line.strip()}
            self.assertEqual(exported & {"open", "open64"}, wanted)

    def test_workloads_twice_and_eager_binding(self):
        for case in CASES[:3] * 2 + CASES[3:]:
            with self.subTest(case=case["name"]):
                env = dict(CLEAN_ENV, LD_PRELOAD=str(ROOT / "fixtures" / case["lib"]),
                           LD_DEBUG="libs,bindings")
                result = collect(case["argv"], env)
                self.assertEqual(result["exit_code"], 0, result["stderr"])
                self.assertEqual(result["stdout"], case["stdout"])
                for marker in ("open", "open64"):
                    self.assertEqual(f"[HOOK] {marker} intercepted" in result["stderr"],
                                     case["marker"] == marker)
                symbol = "open" if case["name"] in ("normal", "no_export") else "open64"
                provider = re.escape(env["LD_PRELOAD"]) if case["fact"] == "EXPECTED_BINDING_OBSERVED" else r"/[^\n ]*/libc\.so\.6"
                pattern = (rf"(?m)^\s*{result['pid']}:\s+binding file "
                           + re.escape(case["argv"][0]) + rf" \[0\] to {provider} \[0\]:.*"
                           + rf"symbol [`']{symbol}'")
                self.assertRegex(result["stderr"], pattern, "ENVIRONMENT: direct PID binding must reproduce")

    def test_static_or_no_export_secondary(self):
        result = collect(["make", "-C", "fixtures", "static"])
        if result["exit_code"]:
            self.skipTest("static compilation unavailable; valid no-export hook is secondary: " + result["stderr"])
        metadata = checked(["readelf", "--wide", "-h", "-l", "-d", "fixtures/app_static"])
        checked(["readelf", "--wide", "--dyn-syms", "fixtures/app_static"])
        self.assertRegex(metadata, r"Type:\s+EXEC\b")
        self.assertNotRegex(metadata, r"(?m)^\s*(INTERP|DYNAMIC)\s")
        self.assertNotIn("(NEEDED)", metadata)
        self.assertIn("There is no dynamic section", metadata)


if __name__ == "__main__":
    unittest.main()
