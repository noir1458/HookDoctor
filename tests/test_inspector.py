import argparse
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from hookdoctor.cli import analyze
from hookdoctor.inspector import Inspector, collector_environment, parse_metadata, parse_nm, parse_symbols, split_version
from hookdoctor.models import AnalysisError, Report, Request
from hookdoctor.process import ProcessResult
from support import ROOT, assert_schema, check, codes, linux_only


def table(rows):
    return f"Symbol table '.dynsym' contains {len(rows)} entries:\n" + "\n".join(
        f" {index}: 0000000000000000 0 FUNC {row}" for index, row in enumerate(rows)) + "\n"


def metadata(elf_type="EXEC", segments=(), needed=False):
    rows = "\n".join(f" {name} 0x000000 0x000000 0x000000 0x000001 0x000001 R 0x1" for name in segments)
    interp = " [Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]\n" if "INTERP" in segments else ""
    dynamic = "There is no dynamic section in this file."
    if "DYNAMIC" in segments:
        dynamic = f"Dynamic section at offset 0x0000 contains {2 if needed else 1} entries:\n"
        if needed:
            dynamic += " 0x00000001 (NEEDED) Shared library: [libc.so.6]\n"
        dynamic += " 0x00000000 (NULL) 0x0\n"
    return f"ELF Header:\n Class: ELF64\n Type: {elf_type}\n Machine: Advanced Micro Devices X86-64\n Number of program headers: {len(segments)}\nProgram Headers:\n{rows}\n{interp}{dynamic}\n"


class ParserTests(unittest.TestCase):
    def test_static_build_failure_is_skipped_with_reason(self):
        from test_fixtures import FixtureGate
        with patch("test_fixtures.collect", return_value={"exit_code": 1, "stderr": "missing libc.a"}), patch("test_fixtures.checked") as inspect, self.assertRaises(unittest.SkipTest) as caught:
            FixtureGate("test_static_or_no_export_secondary").test_static_or_no_export_secondary()
        self.assertIn("missing libc.a", str(caught.exception))
        self.assertIn("no-export", str(caught.exception))
        inspect.assert_not_called()

    def test_versions_and_visibility(self):
        parsed = parse_symbols(table(["GLOBAL DEFAULT UND open64@GLIBC_2.2.5 (2)",
                                      "GLOBAL DEFAULT 12 open@@TEST_1", "GLOBAL HIDDEN 12 secret",
                                      "WEAK PROTECTED 12 visible", "LOCAL DEFAULT 12 local"]))
        self.assertEqual(parsed[0].name, "open64")
        self.assertEqual(parsed[0].version, "GLIBC_2.2.5")
        self.assertEqual(parsed[1].raw_name, "open@@TEST_1")
        self.assertEqual({s.name for s in parsed if s.exported}, {"open", "visible"})
        self.assertEqual(split_version("_Zfoo"), ("_Zfoo", None))
        for raw in ("foo@@@bad", "foo@", "a b"):
            with self.assertRaises(ValueError):
                split_version(raw)

    def test_missing_table_and_truncation_are_not_absence(self):
        for output in ("", "garbage", table(["GLOBAL DEFAULT UND open"]).replace("1 entries", "2 entries")):
            with self.subTest(output=output), self.assertRaises(ValueError):
                parse_symbols(output)
        self.assertEqual(parse_symbols("", allow_empty=True), [])
        self.assertEqual(parse_nm(""), set())
        with self.assertRaises(ValueError):
            parse_nm("unexpected data")

    def test_static_requires_all_properties(self):
        self.assertTrue(parse_metadata("app", metadata()).static)
        self.assertFalse(parse_metadata("app", metadata(segments=("INTERP", "DYNAMIC"), needed=True)).static)
        self.assertFalse(parse_metadata("app", metadata("DYN")).static)
        self.assertFalse(parse_metadata("app", metadata(segments=("DYNAMIC",))).static)
        with self.assertRaises(ValueError):
            parse_metadata("app", metadata().replace("Number of program headers: 0", "Number of program headers: 1"))
        with self.assertRaises(ValueError):
            parse_metadata("app", metadata(segments=("DYNAMIC",)).replace("1 entries", "2 entries"))

    def test_collector_environment_removes_all_loader_settings(self):
        parent = {"LD_PRELOAD": "bad", "LD_CUSTOM": "bad", "LD_LIBRARY_PATH": "bad", "LC_ALL": "ko_KR", "KEEP": "ok"}
        result = collector_environment(parent)
        self.assertEqual(result, {"LC_ALL": "C", "KEEP": "ok"})
        self.assertEqual(parent["LD_PRELOAD"], "bad")

    def test_collector_failed_timeout_limit_flags(self):
        for result, expected, code in ((ProcessResult(1, 1, b"", b"bad"), "COLLECTOR_FAILED", 3),
                                      (ProcessResult(1, -15, b"partial", b"", timed_out=True), "TIMEOUT", 4),
                                      (ProcessResult(1, -15, b"partial", b"", output_limited=True), "OUTPUT_LIMIT", 5)):
            report = Report(Request(["./app"], None, "/hook", "open", str(ROOT)))
            with patch("hookdoctor.inspector.run_bounded", return_value=result), self.assertRaises(AnalysisError) as caught:
                Inspector(report, 64).collect("readelf", "--dyn-syms", "/hook")
            self.assertEqual(caught.exception.code, expected)
            self.assertEqual(caught.exception.exit_code, code)
            self.assertEqual(report.facts, [])
            self.assertTrue(report.evidence)


@linux_only
class InspectorIntegrationTests(unittest.TestCase):
    def test_setid_hook_separator_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            shutil.copy2(ROOT / "fixtures/app_normal", target)
            for mode, expected in ((0o4644, "INPUT_INVALID"), (0o4755, "UNSUPPORTED_ENVIRONMENT"),
                                   (0o2755, "UNSUPPORTED_ENVIRONMENT")):
                target.chmod(mode)
                code, report = check([target])
                self.assertEqual(code, 3)
                self.assertEqual(report["errors"][0]["code"], expected)
                self.assertFalse(report["run"]["attempted"])
            for name in ("hook space.so", "hook:colon.so"):
                lib = Path(temp) / name
                shutil.copy2(ROOT / "fixtures/libhook_open.so", lib)
                code, report = check([ROOT / "fixtures/app_normal"], lib=lib)
                self.assertEqual(code, 3)
                self.assertFalse(report["run"]["attempted"])

    def test_dynamic_exec_and_static_pie(self):
        from test_fixtures import checked, collect
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            checked(["cc", "-O2", "-no-pie", "fixtures/app.c", "-o", str(target)])
            code, report = check([target])
            self.assertEqual(code, 0, report["errors"])
            self.assertNotIn("STATIC_EXECUTABLE", codes(report))
            self.assertTrue(report["run"]["attempted"])
            built = collect(["cc", "-O2", "-static-pie", "fixtures/app.c", "-o", str(target)])
            if built["exit_code"]:
                self.skipTest("static PIE compiler support absent")
            code, report = check([target])
            self.assertEqual(code, 3)
            self.assertEqual(report["errors"][0]["code"], "UNSUPPORTED_ENVIRONMENT")
            self.assertNotIn("STATIC_EXECUTABLE", codes(report))
            self.assertFalse(report["run"]["attempted"])

    def test_analyzer_errors_have_schema_and_no_target(self):
        options = argparse.Namespace(lib=str(ROOT / "fixtures/libhook_open.so"), symbol="open", timeout=10, max_output_bytes=5242880)
        for error in (AnalysisError("TIMEOUT", "readelf collector timeout", 4),
                      AnalysisError("COLLECTOR_FAILED", "readelf failed", 3)):
            with patch("hookdoctor.inspector.Inspector.collect", side_effect=error), patch("hookdoctor.cli.trace") as trace:
                report, code = analyze(options, [str(ROOT / "fixtures/app_normal")])
                self.assertEqual(code, error.exit_code)
                assert_schema(report.to_dict())
                trace.assert_not_called()

    def test_architecture_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "aarch64"
            data = bytearray((ROOT / "fixtures/app_normal").read_bytes())
            data[18:20] = (183).to_bytes(2, "little")
            target.write_bytes(data)
            target.chmod(0o755)
            code, report = check([target])
            self.assertEqual(code, 3)
            self.assertEqual(report["errors"][0]["code"], "UNSUPPORTED_ENVIRONMENT")
            self.assertFalse(report["run"]["attempted"])
