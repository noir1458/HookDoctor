import copy
import unittest

from hookdoctor.diagnose import runtime_facts, static_facts
from hookdoctor.models import Elf, Report, Request, Symbol
from hookdoctor.tracer import TraceFacts


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.report = Report(Request(["./target"], "/target", "/hook", "open", "/"), status="INCONCLUSIVE")
        self.report.run.trace_complete = True
        refs = [self.report.add_evidence("readelf", "test observation") for _ in range(3)]
        self.target = Elf("/target", "DYN", "ELF64", "x86-64", "/loader", True, ["libc.so.6"], True,
                          [Symbol("open64@GLIBC_2.2.5", "open64", "GLIBC_2.2.5", "GLOBAL", "DEFAULT", "UND")],
                          refs[0], refs[0])
        self.hook = Elf("/hook", "DYN", "ELF64", "x86-64", None, True, [], False,
                        [Symbol("open", "open", None, "GLOBAL", "DEFAULT", "12")], refs[1], refs[1], refs[1])
        self.trace = TraceFacts(libc_variant=[refs[2]])

    def test_exact_conditional_rule_and_references(self):
        static_facts(self.report, self.target, self.hook)
        runtime_facts(self.report, self.target, self.hook, self.trace)
        self.assertEqual(len(self.report.diagnoses), 1)
        diagnosis = self.report.diagnoses[0]
        self.assertEqual(diagnosis["id"], "SYMBOL_VARIANT_MISMATCH")
        self.assertEqual(diagnosis["status"], "CONDITIONAL")
        self.assertEqual(diagnosis["condition"], "If this workload executes the observed open64 path, a hook exporting only open cannot intercept that open64 call.")
        self.assertEqual(self.report.observations.invocation, "UNKNOWN")
        self.report.validate_references()

    def test_each_missing_condition_withholds_diagnosis(self):
        for missing in ("requested", "import", "export", "variant_exported", "runtime", "complete", "error"):
            with self.subTest(missing=missing):
                report, target, hook, trace = copy.deepcopy((self.report, self.target, self.hook, self.trace))
                if missing == "requested": report.request.expected_symbol = "open64"
                if missing == "import": target.symbols.clear()
                if missing == "export": hook.symbols.clear()
                if missing == "variant_exported": hook.symbols.append(Symbol("open64", "open64", None, "GLOBAL", "DEFAULT", "12"))
                if missing == "runtime": trace.libc_variant.clear()
                if missing == "complete": report.run.trace_complete = False
                if missing == "error": report.status = "ERROR"
                static_facts(report, target, hook)
                runtime_facts(report, target, hook, trace)
                self.assertEqual(report.diagnoses, [])

    def test_eager_binding_never_changes_invocation(self):
        for argument in ("--call", "--skip"):
            report = copy.deepcopy(self.report)
            report.request.target_argv.append(argument)
            runtime_facts(report, self.target, self.hook, self.trace)
            self.assertEqual(report.status, "INCONCLUSIVE")
            self.assertEqual(report.observations.invocation, "UNKNOWN")
            self.assertEqual(len(report.diagnoses), 1)

    def test_expected_binding_is_fact_with_unknown_invocation(self):
        self.trace.expected = [self.report.evidence[0]["id"]]
        self.trace.libc_variant.clear()
        runtime_facts(self.report, self.target, self.hook, self.trace)
        self.assertIn("EXPECTED_BINDING_OBSERVED", {f["code"] for f in self.report.facts})
        self.assertEqual(self.report.status, "INCONCLUSIVE")
        self.assertEqual(self.report.observations.invocation, "UNKNOWN")

    def test_no_inferred_suffix_families(self):
        self.report.request.expected_symbol = "read"
        runtime_facts(self.report, self.target, self.hook, self.trace)
        self.assertEqual(self.report.diagnoses, [])

    def test_missing_exports_are_facts_without_runtime(self):
        self.hook.symbols.clear()
        static_facts(self.report, self.target, self.hook)
        self.assertIn("SYMBOL_NOT_EXPORTED", {f["code"] for f in self.report.facts})
        self.assertEqual(self.report.diagnoses, [])
