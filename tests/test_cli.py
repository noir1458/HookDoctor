import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from hookdoctor.cli import main
from support import ENV, ROOT, check, codes, invoke, linux_only


class ParsingTests(unittest.TestCase):
    def test_invalid_options_launch_nothing(self):
        base = ["check", "--lib", "./x", "--symbol", "open"]
        invalid = [["--timeout", x] for x in ("0", "-1", "nan", "inf", "-inf", "wat")]
        invalid += [["--max-output-bytes", x] for x in ("0", "-1", "1.5", "nan")]
        invalid += [["--symbol", x] for x in ("", "open@GLIBC_2.2.5", "a b", "a\nb")]
        with patch("hookdoctor.process.subprocess.Popen") as launch:
            for args in invalid:
                with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        main([*base, *args, "--", "./app"])
                    self.assertEqual(caught.exception.code, 2)
            for args in (base, [*base, "./app"], [*base, "--"], [*base, "--", ""]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    main(args)
                self.assertEqual(caught.exception.code, 2)
            launch.assert_not_called()

    def test_help_and_version(self):
        for args, phrase in ((["--help"], "check"), (["--version"], "0.3.0"), (["check", "--help"], "--timeout")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as caught:
                main(args)
            self.assertEqual(caught.exception.code, 0)
            self.assertIn(phrase, output.getvalue())


@linux_only
class CLIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build outside the CLI, whose contract never compiles or repairs input.
        from test_fixtures import checked
        checked(["make", "-C", "fixtures", "all"])

    def test_acceptance_matrix(self):
        cases = json.loads((ROOT / "fixtures/expected_cases.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                code, report = check(case["argv"], lib=ROOT / "fixtures" / case["lib"], symbol=case["symbol"])
                self.assertEqual(code, 0, report["errors"])
                self.assertEqual(report["status"], "INCONCLUSIVE")
                self.assertEqual(report["run"]["target_exit_code"], 0)
                self.assertTrue(report["run"]["trace_complete"])
                self.assertEqual(report["run"]["stdout"], case["stdout"])
                self.assertEqual(bool(report["diagnoses"]), case["mismatch"])
                if case["fact"]:
                    self.assertIn(case["fact"], codes(report))
                for marker in ("open", "open64"):
                    self.assertEqual(f"[HOOK] {marker} intercepted" in report["run"]["stderr"], case["marker"] == marker)

    def test_invalid_inputs_one_json_no_run(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "bad"
            invalid.write_text("#!/bin/sh\nexit 0\n")
            invalid.chmod(0o755)
            for argv, lib in (([ROOT / "fixtures/app_normal"], Path(temp) / "missing.so"),
                              ([ROOT / "fixtures/app_normal"], invalid), ([invalid], None),
                              ([Path(temp) / "missing"], None), (["echo"], None)):
                with self.subTest(argv=argv, lib=lib):
                    code, report = check(argv, lib=lib)
                    self.assertEqual(code, 3)
                    self.assertFalse(report["run"]["attempted"])
                    self.assertEqual(report["status"], "ERROR")

    def test_nonexecutable_hook_spaces_literal_argv_and_parent_environment(self):
        before = dict(os.environ)
        cwd_before = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="hookdoctor target ") as temp:
            target = Path(temp) / "target with space"
            shutil.copy2(sys.executable, target)
            # The hook must not have spaces; its lack of execute permission is valid.
            with tempfile.TemporaryDirectory() as hook_temp:
                hook = Path(hook_temp) / "hook.so"
                shutil.copyfile(ROOT / "fixtures/libhook_open.so", hook)
                hook.chmod(0o644)
                literal = "$(touch SHOULD_NOT_EXIST); `echo no` *"
                script = "import os,sys,json; print(json.dumps([os.getcwd(),sys.argv[1],os.environ['ORDINARY']]))"
                env = dict(ENV, ORDINARY="preserved")
                code, report = check([target, "-c", script, literal], lib=hook, env=env, cwd=temp)
                self.assertEqual(code, 0, report["errors"])
                self.assertEqual(json.loads(report["run"]["stdout"]), [temp, literal, "preserved"])
                self.assertFalse((Path(temp) / "SHOULD_NOT_EXIST").exists())
        self.assertEqual(os.environ, before)
        self.assertEqual(os.getcwd(), cwd_before)

    def test_nonzero_signal_and_non_utf8_target(self):
        for script, expected in (("import sys;sys.exit(7)", 7),
                                  ("import os,signal;os.kill(os.getpid(),signal.SIGTERM)", -signal.SIGTERM),
                                  ("import os;os.write(1,b'\\xffok')", 0)):
            with self.subTest(script=script):
                code, report = check([sys.executable, "-c", script])
                self.assertEqual(code, 0, report["errors"])
                self.assertEqual(report["run"]["target_exit_code"], expected)
                self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertIn("\ufffdok", report["run"]["stdout"])

    def test_timeout_flood_and_child_pipe_json(self):
        cases = [("import time;print('ready',flush=True);time.sleep(5)", ["--timeout", "0.3"], 4),
                 ("import os\nwhile True: os.write(1,b'x'*65536)", ["--max-output-bytes", "262144"], 5),
                 ("import os,time\nif os.fork()==0: time.sleep(5)\nelse: os._exit(0)", ["--timeout", "0.3"], 4)]
        for script, options, wanted in cases:
            with self.subTest(wanted=wanted, script=script):
                code, report = check([sys.executable, "-c", script], options=options)
                self.assertEqual(code, wanted, report["errors"])
                self.assertTrue(report["run"]["attempted"])
                self.assertFalse(report["run"]["trace_complete"])
                self.assertTrue(report["run"]["timed_out"] if wanted == 4 else report["run"]["output_limited"])
                self.assertEqual(report["diagnoses"], [])
                if wanted == 5:
                    self.assertLessEqual(len(report["run"]["stdout"].encode()) + len(report["run"]["stderr"].encode()), 262144)

    def test_collector_output_limit_is_not_target_failure(self):
        code, report = check([ROOT / "fixtures/app_normal"], options=["--max-output-bytes", "20"])
        self.assertEqual(code, 5)
        self.assertFalse(report["run"]["attempted"])
        self.assertTrue(report["run"]["output_limited"])
        self.assertIn("collector", report["errors"][0]["message"])

    def test_real_collector_failure_timeout_and_output_json(self):
        real_readelf = shutil.which("readelf")
        with tempfile.TemporaryDirectory() as temp:
            wrapper = Path(temp) / "readelf"
            for body, wanted in (("raise SystemExit(9)", 3), ("import time;time.sleep(8)", 4),
                                 ("import os\nwhile True: os.write(1,b'x'*4096)", 5)):
                wrapper.write_text(f"#!{sys.executable}\nimport os,sys\nif sys.argv[1:] == ['--version']:\n os.execv({real_readelf!r},[{real_readelf!r},'--version'])\n{body}\n")
                wrapper.chmod(0o755)
                with self.subTest(wanted=wanted):
                    code, report = check([ROOT / "fixtures/app_normal"], env=dict(ENV, PATH=temp + os.pathsep + ENV["PATH"]), options=["--max-output-bytes", "8192"])
                    self.assertEqual(code, wanted, report["errors"])
                    self.assertFalse(report["run"]["attempted"])
                    self.assertNotIn("SYMBOL_NOT_EXPORTED", codes(report))
                    self.assertEqual(report["run"]["timed_out"], wanted == 4)
                    self.assertEqual(report["run"]["output_limited"], wanted == 5)

    def test_real_static(self):
        from test_fixtures import collect
        built = collect(["make", "-C", "fixtures", "static"])
        if built["exit_code"]:
            self.skipTest("static compiler support absent; no-export covered independently")
        code, report = check([ROOT / "fixtures/app_static"])
        self.assertEqual(code, 0, report["errors"])
        self.assertEqual(report["status"], "NOT_APPLICABLE")
        self.assertIn("STATIC_EXECUTABLE", codes(report))
        self.assertFalse(report["run"]["attempted"])

    def test_human_output_facts_uncertainty_and_next_check(self):
        result = invoke("check", "--lib", str(ROOT / "fixtures/libhook_fixed.so"), "--symbol", "open64", "--", "./fixtures/app_large")
        output = result.stdout.decode()
        self.assertEqual(result.returncode, 0, output)
        self.assertTrue(output.startswith("Requested symbol bound to the hook: confirmed"))
        for phrase in ("Observed facts", "Conditional explanations", "Remaining uncertainty", "Next check", "INCONCLUSIVE concerns", "exit=0"):
            self.assertIn(phrase, output)
