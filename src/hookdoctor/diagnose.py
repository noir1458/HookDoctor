"""Pure rules: no filesystem reads, process launches or fixture knowledge."""
from .tracer import TraceFacts

VARIANTS = {"open": ["open64"]}
INVOCATION_LIMIT = "Loader binding does not establish function invocation or this workload's actual failure cause; invocation is UNKNOWN"


def static_facts(report, target, hook):
    relevant = [report.request.expected_symbol, *VARIANTS.get(report.request.expected_symbol, [])]
    for name in relevant:
        if name in target.imports:
            decorated = ", ".join(s.raw_name for s in target.symbols if s.name == name and s.section == "UND")
            report.add_fact("TARGET_IMPORTS_SYMBOL", f"Target imports {decorated}", [target.symbol_evidence])
        refs = [hook.symbol_evidence, hook.export_evidence]
        if name in hook.exports:
            decorated = ", ".join(s.raw_name for s in hook.symbols if s.name == name and s.exported)
            report.add_fact("HOOK_EXPORTS_SYMBOL", f"Hook {hook.path} exports {decorated}; base-name comparison alone does not establish version compatibility", refs)
        else:
            report.add_fact("SYMBOL_NOT_EXPORTED", f"Hook {hook.path} does not export {name} as an externally visible dynamic symbol", refs)


def runtime_facts(report, target, hook, trace_facts: TraceFacts):
    if trace_facts.loaded:
        report.add_fact("LIBRARY_LOADED", f"Requested hook object was observed loaded: {hook.path}", trace_facts.loaded)
    for binding in report.observations.bindings:
        if binding["symbol"] not in [report.request.expected_symbol, *VARIANTS.get(report.request.expected_symbol, [])]:
            continue
        report.add_fact("BINDING_OBSERVED", f"Direct target {binding['symbol']} version={binding['symbol_version']!r} resolves to {binding['provider_object']}", binding["evidence_ids"])
    if trace_facts.expected:
        report.add_fact("EXPECTED_BINDING_OBSERVED", "Requested symbol bound to the hook: confirmed (symbol resolution only; invocation remains UNKNOWN)", trace_facts.expected)
    if (report.status != "ERROR" and report.run.trace_complete
            and report.request.expected_symbol == "open"
            and "open64" in target.imports and "open" in hook.exports
            and "open64" not in hook.exports and trace_facts.libc_variant):
        report.diagnoses.append(dict(id="SYMBOL_VARIANT_MISMATCH", status="CONDITIONAL",
            message="Target imports and binds open64 to the identified libc object; the requested hook exports open but not open64",
            condition="If this workload executes the observed open64 path, a hook exporting only open cannot intercept that open64 call.",
            evidence_ids=[target.symbol_evidence, hook.symbol_evidence, hook.export_evidence, *trace_facts.libc_variant],
            next_steps=["Add a correct open64 wrapper and rerun the same target argv with the fixed library and --symbol open64"]))
