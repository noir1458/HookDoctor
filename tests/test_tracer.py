import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from hookdoctor.models import AnalysisError, Report, Request
from hookdoctor.process import run_bounded
from hookdoctor.tracer import parse_trace, target_environment, trace
from support import ENV, ROOT, linux_only


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target, self.hook, self.libc, self.other = [Path(self.temp.name) / name for name in ("target", "hook", "libc.so.6", "other")]
        for path in (self.target, self.hook, self.libc, self.other):
            path.touch()
        self.report = Report(Request([str(self.target)], str(self.target), str(self.hook), "open", self.temp.name))
        self.identities = {"libc": {str(self.libc)}, "loader": set()}

    def binding(self, caller=None, provider=None, symbol="open", pid=100):
        return f" {pid}: binding file {caller or self.target} [0] to {provider or self.hook} [0]: normal symbol `{symbol}' [GLIBC_2.2.5]\n"

    def test_target_binding_and_forwarding_distinguished(self):
        self.report.run.stderr = self.binding() + self.binding(caller=self.hook, provider=self.libc)
        facts = parse_trace(self.report, 100, self.identities)
        self.assertEqual(len(self.report.observations.bindings), 1)
        self.assertTrue(facts.expected)
        self.assertFalse(facts.libc_variant)
        self.assertEqual(self.report.observations.library_load, "OBSERVED")
        self.assertEqual(self.report.observations.invocation, "UNKNOWN")

    def test_child_ambiguous_and_unknown_rows_are_excluded(self):
        rows = [self.binding(pid=101), self.binding(caller="target"), self.binding(caller=self.other),
                self.binding().replace("normal symbol", "unknown symbol"), self.binding().replace("[0]", "[1]"),
                self.binding(provider="libc.so.6"), self.binding()[:-1]]
        for line in rows:
            report = Report(self.report.request)
            report.run.stderr = line
            facts = parse_trace(report, 100, self.identities)
            self.assertEqual(report.observations.bindings, [], line)
            self.assertFalse(facts.expected)
            self.assertEqual(report.observations.invocation, "UNKNOWN")

    def test_no_load_without_positive_event(self):
        self.report.run.stderr = f" 100: trying file={self.hook}\n"
        parse_trace(self.report, 100, self.identities)
        self.assertEqual(self.report.observations.library_load, "UNKNOWN")
        self.report.run.stderr = f" 100: calling init: {self.hook}\n"
        parse_trace(self.report, 100, self.identities)
        self.assertEqual(self.report.observations.library_load, "OBSERVED")

    def test_canonical_alias_and_libc_identity(self):
        alias = Path(self.temp.name) / "target-link"
        alias.symlink_to(self.target)
        self.report.run.stderr = self.binding(caller=alias, provider=self.libc, symbol="open64")
        facts = parse_trace(self.report, 100, self.identities)
        self.assertTrue(facts.libc_variant)
        self.assertEqual(self.report.observations.bindings[0]["symbol_version"], "GLIBC_2.2.5")
        impostor = Path(self.temp.name) / "other-libc.so.6"
        impostor.touch()
        report = Report(self.report.request)
        report.run.stderr = self.binding(provider=impostor, symbol="open64")
        self.assertFalse(parse_trace(report, 100, self.identities).libc_variant)

    def test_loader_policy_and_parent_unchanged(self):
        parent = {"LD_PRELOAD": "private inherited value", "LD_DEBUG": "all", "LD_AUDIT": "secret",
                  "LD_DEBUG_OUTPUT": "secret", "LD_TRACE_LOADED_OBJECTS": "1", "LD_LIBRARY_PATH": "/custom", "LD_BIND_NOW": "1", "NORMAL": "kept"}
        env, policy = target_environment("/hook", parent)
        self.assertEqual(env["LD_PRELOAD"], "/hook")
        self.assertEqual(env["LD_DEBUG"], "libs,bindings")
        self.assertEqual(env["LD_LIBRARY_PATH"], "/custom")
        self.assertEqual(env["LD_BIND_NOW"], "1")
        self.assertEqual(env["NORMAL"], "kept")
        for removed in policy["removed"]:
            self.assertNotIn(removed, env)
        self.assertNotIn("secret", repr(policy))
        self.assertEqual(parent["LD_AUDIT"], "secret")

    def test_launch_failure_preserves_attempted_and_policy(self):
        with patch("hookdoctor.tracer.run_bounded", side_effect=OSError("no executable")), self.assertRaises(AnalysisError) as error:
            trace(self.report, self.identities, timeout=1, max_bytes=100)
        self.assertEqual(error.exception.code, "LAUNCH_FAILED")
        self.assertTrue(self.report.run.attempted)
        self.assertIsNone(self.report.run.target_exit_code)
        self.assertIsNotNone(self.report.run.loader_environment)


@linux_only
class BoundedRunnerTests(unittest.TestCase):
    def run_script(self, code, timeout=1, cap=4096):
        return run_bounded([sys.executable, "-c", code], env=ENV, timeout=timeout, max_bytes=cap)

    def test_combined_output_cap_and_exact_boundary(self):
        result = self.run_script("import os;os.write(1,b'a'*50);os.write(2,b'b'*50)", cap=100)
        self.assertTrue(result.complete)
        self.assertEqual(len(result.stdout) + len(result.stderr), 100)
        result = self.run_script("import os\nwhile True: os.write(1,b'a'*1000);os.write(2,b'b'*1000)", cap=8192)
        self.assertTrue(result.output_limited)
        self.assertLessEqual(len(result.stdout) + len(result.stderr), 8192)

    def test_child_pipe_timeout_and_owned_group_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            sentinel = Path(temp) / "escaped"
            code = f"import os,time\nif os.fork()==0:\n time.sleep(1.0)\n open({str(sentinel)!r},'w').write('bad')\nelse: os._exit(0)"
            unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(10)"], env=ENV, start_new_session=True)
            try:
                start = time.monotonic()
                result = self.run_script(code, timeout=0.2)
                self.assertTrue(result.timed_out)
                self.assertEqual(result.returncode, 0)
                self.assertLess(time.monotonic() - start, 1.5)
                time.sleep(0.5)
                self.assertFalse(sentinel.exists())
                self.assertIsNone(unrelated.poll())
            finally:
                unrelated.terminate()
                unrelated.wait(timeout=5)

    def test_term_ignoring_target_is_killed(self):
        result = self.run_script("import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ready',flush=True);time.sleep(10)", timeout=0.3)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, -signal.SIGKILL)
        self.assertIn(b"ready", result.stdout)

    def test_interruption_cleans_owned_group(self):
        import hookdoctor.process as process
        original_popen = process.subprocess.Popen
        created = []
        def capture(*args, **kwargs):
            proc = original_popen(*args, **kwargs)
            created.append(proc)
            return proc
        with patch.object(process.subprocess, "Popen", side_effect=capture), patch.object(process.selectors.EpollSelector, "select", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_script("import time;time.sleep(10)")
        self.assertEqual(len(created), 1)
        self.assertIsNotNone(created[0].poll())
        self.assertTrue(created[0].stdout.closed)
