"""Schema v0.3 and internal observation structures (no terminal rendering)."""
from dataclasses import asdict, dataclass, field


@dataclass
class Request:
    target_argv: list[str]
    resolved_executable: str | None
    hook_library: str
    expected_symbol: str
    cwd: str


@dataclass
class Run:
    attempted: bool = False
    target_exit_code: int | None = None
    timed_out: bool = False
    output_limited: bool = False
    trace_complete: bool = False
    stdout: str = ""
    stderr: str = ""
    loader_environment: dict | None = None


@dataclass
class Observations:
    library_load: str = "NOT_RUN"
    invocation: str = "UNKNOWN"
    bindings: list[dict] = field(default_factory=list)


@dataclass
class Report:
    request: Request
    schema_version: str = "0.3"
    status: str = "ERROR"
    facts: list[dict] = field(default_factory=list)
    diagnoses: list[dict] = field(default_factory=list)
    observations: Observations = field(default_factory=Observations)
    run: Run = field(default_factory=Run)
    evidence: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def add_evidence(self, source, summary, raw=""):
        ident = f"ev-{len(self.evidence) + 1:03d}"
        # Raw evidence is an excerpt, never a second unbounded trace copy.
        used = getattr(self, "_raw_bytes", 0)
        remaining = max(0, 65536 - used)
        excerpt = raw.encode("utf-8")[:min(4096, remaining)].decode("utf-8", "ignore")
        self.evidence.append(dict(id=ident, source=source, summary=summary, raw_excerpt=excerpt))
        self._raw_bytes = used + len(excerpt.encode("utf-8"))
        return ident

    def add_fact(self, code, message, evidence_ids):
        self.facts.append(dict(id=f"fact-{len(self.facts) + 1:03d}", code=code,
                               status="CONFIRMED", message=message, evidence_ids=evidence_ids))

    def validate_references(self):
        available = {e["id"] for e in self.evidence}
        assert len(available) == len(self.evidence)
        for item in self.facts + self.diagnoses + self.observations.bindings:
            assert item["evidence_ids"] and set(item["evidence_ids"]) <= available
        assert self.observations.invocation == "UNKNOWN"

    def to_dict(self):
        self.validate_references()
        data = asdict(self)
        # Keep the published top-level order independent of constructor defaults.
        return {key: data[key] for key in ("schema_version", "status", "request", "facts",
                "diagnoses", "observations", "run", "evidence", "limitations", "errors")}


class AnalysisError(Exception):
    def __init__(self, code, message, exit_code=3):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


@dataclass(frozen=True)
class Symbol:
    raw_name: str
    name: str
    version: str | None
    binding: str
    visibility: str
    section: str

    @property
    def exported(self):
        return (self.section != "UND" and self.binding in {"GLOBAL", "WEAK", "UNIQUE"}
                and self.visibility in {"DEFAULT", "PROTECTED"})


@dataclass
class Elf:
    path: str
    elf_type: str
    elf_class: str
    machine: str
    interpreter: str | None
    dynamic: bool
    needed: list[str]
    eager: bool
    symbols: list[Symbol] = field(default_factory=list)
    header_evidence: str | None = None
    symbol_evidence: str | None = None
    export_evidence: str | None = None

    @property
    def static(self):
        return self.elf_type == "EXEC" and not self.interpreter and not self.dynamic and not self.needed

    @property
    def imports(self):
        return {s.name for s in self.symbols if s.section == "UND"}

    @property
    def exports(self):
        return {s.name for s in self.symbols if s.exported}
