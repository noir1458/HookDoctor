"""Both renderers consume the same report; no diagnosis rules live here."""
import json


def render_json(report):
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_terminal(report):
    report.validate_references()
    lines = []
    success = next((fact for fact in report.facts if fact["code"] == "EXPECTED_BINDING_OBSERVED"), None)
    if success:
        lines.append(success["message"])
    lines += [f"HookDoctor: {report.status}",
              f"Target argv: {json.dumps(report.request.target_argv, ensure_ascii=False)}",
              f"Executable: {report.request.resolved_executable}",
              f"Hook: {report.request.hook_library}; requested symbol: {report.request.expected_symbol}",
              f"Working directory: {report.request.cwd}", "", "Observed facts"]
    lines += [f"- {f['code']}: {f['message']} [{', '.join(f['evidence_ids'])}]" for f in report.facts] or ["- No confirmed facts collected"]
    lines += [f"- Target execution: attempted={report.run.attempted}, exit={report.run.target_exit_code}, trace_complete={report.run.trace_complete}"]
    for ev in report.evidence:
        if ev["source"] == "readelf" and ev["summary"].startswith("Inspected "):
            lines.append(f"- Inspection [{ev['id']}]: {ev['summary']}")
    lines += ["", "Conditional explanations"]
    for diagnosis in report.diagnoses:
        lines += [f"- {diagnosis['id']}: {diagnosis['message']}", f"  Condition: {diagnosis['condition']}",
                  f"  Evidence: {', '.join(diagnosis['evidence_ids'])}"]
    if not report.diagnoses:
        lines.append("- No supported conditional explanation established")
    lines += ["", "Remaining uncertainty"]
    if report.status == "INCONCLUSIVE":
        lines.append("- INCONCLUSIVE concerns the current workload's cause; confirmed facts above remain valid.")
    lines += [f"- {item}" for item in report.limitations]
    for error in report.errors:
        lines.append(f"- ERROR {error['code']}: {error['message']}")
    lines += ["", "Next check"]
    steps = [step for d in report.diagnoses for step in d["next_steps"]]
    if not steps:
        if any(f["code"] == "SYMBOL_NOT_EXPORTED" for f in report.facts):
            steps = ["Check the hook's dynamic exports with nm -D --defined-only, add the exact required wrapper, then rerun the same workload."]
        elif report.status == "ERROR":
            steps = ["Resolve the reported input/environment/collection error, then repeat this command."]
        elif report.status == "NOT_APPLICABLE":
            steps = ["Use a dynamically linked target to investigate glibc LD_PRELOAD interposition."]
        else:
            steps = ["Use a debugger/function-entry observer or controlled source and arguments to establish invocation; retain raw version evidence."]
    lines += [f"- {step}" for step in steps]
    return "\n".join(lines)
