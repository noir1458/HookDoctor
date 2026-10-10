"""Fail-closed GNU ELF collectors. An empty failed table is never absence proof."""
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys

from .models import AnalysisError, Elf, Symbol
from .process import run_bounded


def collector_environment(parent=None):
    env = {k: v for k, v in (os.environ if parent is None else parent).items()
           if not k.startswith("LD_")}
    env["LC_ALL"] = "C"
    return env


def same_object(left, right):
    try:
        return os.path.samefile(left, right)
    except (OSError, ValueError, TypeError):
        return False


def mapped_glibc_objects():
    """Conservative identity anchors, not guessed provider basename matches."""
    result = {"libc": set(), "loader": set()}
    try:
        with open("/proc/self/maps", "rb") as handle:
            data = handle.read(262145)
        if len(data) > 262144:
            return result
        for line in data.decode("utf-8", "replace").splitlines():
            fields = line.split(None, 5)
            if len(fields) == 6 and fields[5].startswith("/"):
                path = fields[5]
                if Path(path).name == "libc.so.6":
                    result["libc"].add(str(Path(path).resolve()))
                if Path(path).name == "ld-linux-x86-64.so.2":
                    result["loader"].add(str(Path(path).resolve()))
    except OSError:
        pass
    return result


class Inspector:
    def __init__(self, report, max_bytes):
        self.report, self.max_bytes = report, max_bytes
        self.env = collector_environment()
        self.tools = {}
        self.identities = {"libc": set(), "loader": set()}

    def collect(self, tool, *args):
        argv = [self.tools.get(tool, tool), *args]
        try:
            result = run_bounded(argv, env=self.env, cwd=self.report.request.cwd,
                                 timeout=5, max_bytes=self.max_bytes)
        except OSError as exc:
            raise AnalysisError("COLLECTOR_FAILED", f"{tool}: {exc}") from exc
        stdout = result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace")
        if not result.complete or result.returncode != 0 or stderr.strip():
            self.report.add_evidence(tool if tool in {"nm", "readelf"} else "validation",
                                     f"Collector did not complete successfully: {argv!r}", stdout + stderr)
            if result.timed_out:
                self.report.run.timed_out = True
                raise AnalysisError("TIMEOUT", f"{tool} collector exceeded 5 seconds", 4)
            if result.output_limited:
                self.report.run.output_limited = True
                raise AnalysisError("OUTPUT_LIMIT", f"{tool} collector exceeded {self.max_bytes} captured bytes", 5)
            raise AnalysisError("COLLECTOR_FAILED", f"{tool} returned {result.returncode} or diagnostic stderr: {stderr[:500]}")
        return stdout

    def platform(self):
        if sys.version_info < (3, 11):
            raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "Requires Python 3.11 or newer")
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "Requires Linux x86-64/glibc; on macOS use scripts/dev.sh")
        try:
            libc = os.confstr("CS_GNU_LIBC_VERSION")
        except (ValueError, OSError):
            libc = None
        if not libc or not libc.startswith("glibc "):
            raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "Unable to establish a glibc runtime")
        for tool in ("readelf", "nm"):
            found = shutil.which(tool)
            if not found:
                raise AnalysisError("COLLECTOR_FAILED", f"Required GNU tool is unavailable: {tool}")
            self.tools[tool] = found
            version = self.collect(tool, "--version")
            if not version.startswith(f"GNU {tool} "):
                raise AnalysisError("UNSUPPORTED_ENVIRONMENT", f"Requires GNU {tool}")
        self.identities = mapped_glibc_objects()
        self.report.add_evidence("validation", f"Linux x86-64; {libc}; GNU readelf/nm available; helper environment clears LD_* and sets LC_ALL=C")

    def paths(self):
        request = self.report.request
        raw_target = request.target_argv[0]
        if "/" not in raw_target:
            raise AnalysisError("INPUT_INVALID", "Target must be an explicit path (for example ./app); PATH lookup is unsupported")
        try:
            target = Path(raw_target).resolve(strict=True)
            request.resolved_executable = str(target)
        except (OSError, ValueError, RuntimeError) as exc:
            raise AnalysisError("INPUT_INVALID", f"Cannot resolve target: {exc}") from exc
        try:
            hook = Path(request.hook_library).resolve()
            request.hook_library = str(hook)
        except (OSError, ValueError, RuntimeError) as exc:
            raise AnalysisError("INPUT_INVALID", f"Cannot resolve hook: {exc}") from exc
        if any(c.isspace() or c == ":" for c in str(hook)):
            raise AnalysisError("INPUT_INVALID", "A single LD_PRELOAD path cannot contain whitespace or colon")
        for path, is_target in ((target, True), (hook, False)):
            try:
                mode = path.stat().st_mode
            except FileNotFoundError as exc:
                if not is_target:
                    ev = self.report.add_evidence("validation", f"Hook path does not exist: {path}")
                    self.report.add_fact("LIBRARY_NOT_FOUND", f"Hook library not found: {path}", [ev])
                raise AnalysisError("INPUT_INVALID", f"Missing input: {path}") from exc
            if not stat.S_ISREG(mode) or not os.access(path, os.R_OK):
                raise AnalysisError("INPUT_INVALID", f"Expected readable regular file: {path}")
            if is_target and not os.access(path, os.X_OK):
                raise AnalysisError("INPUT_INVALID", f"Target is not executable: {path}")
            if is_target and mode & (stat.S_ISUID | stat.S_ISGID):
                raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "set-user-ID/set-group-ID targets may use secure execution")
            if is_target and hasattr(os, "getxattr"):
                try:
                    capabilities = os.getxattr(path, "security.capability")
                except OSError as exc:
                    # ENODATA and ENOTSUP mean no known file-capability case.
                    import errno
                    if exc.errno not in {errno.ENODATA, errno.ENOTSUP}:
                        raise AnalysisError("UNSUPPORTED_ENVIRONMENT", f"Cannot inspect target file capabilities: {exc}") from exc
                else:
                    if capabilities:
                        raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "File-capability target may use secure execution")
            try:
                with path.open("rb") as handle:
                    magic = handle.read(4)
            except OSError as exc:
                raise AnalysisError("INPUT_INVALID", f"Cannot read input: {path}: {exc}") from exc
            if magic != b"\x7fELF":
                raise AnalysisError("INPUT_INVALID", f"Expected ELF file, scripts/launchers unsupported: {path}")
        self.report.add_evidence("validation", "Target is a readable executable regular ELF; hook is a readable regular ELF; no known set-ID/file-capability case")

    def inspect(self, path, *, hook=False):
        metadata = self.collect("readelf", "--wide", "-h", "-l", "-d", path)
        try:
            elf = parse_metadata(path, metadata)
        except ValueError as exc:
            self.report.add_evidence("readelf", f"Unrecognized metadata for {path}", metadata)
            raise AnalysisError("COLLECTOR_FAILED", str(exc)) from exc
        elf.header_evidence = self.report.add_evidence("readelf", f"Inspected {path}: {elf.elf_type}, {elf.elf_class}, {elf.machine}; PT_INTERP={elf.interpreter!r}; PT_DYNAMIC={elf.dynamic}; DT_NEEDED={elf.needed!r}; eager={elf.eager}", metadata)
        if elf.elf_class != "ELF64" or elf.machine != "Advanced Micro Devices X86-64":
            raise AnalysisError("UNSUPPORTED_ENVIRONMENT", f"Unsupported ELF class/machine: {path}")
        if hook:
            if elf.elf_type != "DYN" or elf.interpreter or not elf.dynamic:
                raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "Hook must be an ET_DYN shared library, not an executable")
        elif not elf.static:
            if (elf.elf_type not in {"EXEC", "DYN"} or not elf.dynamic or not elf.interpreter
                    or not any(same_object(elf.interpreter, loader) for loader in self.identities["loader"])):
                raise AnalysisError("UNSUPPORTED_ENVIRONMENT", "Unsupported/ambiguous target ELF or PT_INTERP; static PIE is deferred")
        table = self.collect("readelf", "--wide", "--dyn-syms", path)
        try:
            elf.symbols = parse_symbols(table, allow_empty=elf.static)
        except ValueError as exc:
            self.report.add_evidence("readelf", f"Unrecognized/incomplete dynamic symbols for {path}", table)
            raise AnalysisError("COLLECTOR_FAILED", str(exc)) from exc
        relevant = {self.report.request.expected_symbol}
        if "open" in relevant:
            relevant.add("open64")
        excerpt = "\n".join(line for line in table.splitlines() if any(
            re.search(r"\b" + re.escape(name) + r"(?:@|\s|$)", line) for name in relevant))
        elf.symbol_evidence = self.report.add_evidence("readelf", f"Complete dynamic symbol table inspected: {path}; {len(elf.symbols)} named entries (raw excerpt shows requested/variant rows)", excerpt or table[:200])
        if hook:
            exports = self.collect("nm", "-D", "--defined-only", path)
            try:
                nm_names = parse_nm(exports)
            except ValueError as exc:
                raise AnalysisError("COLLECTOR_FAILED", str(exc)) from exc
            visible = {s.raw_name for s in elf.symbols if s.exported}
            if not visible <= nm_names:
                raise AnalysisError("COLLECTOR_FAILED", "GNU nm and readelf disagree on defined visible hook exports")
            elf.export_evidence = self.report.add_evidence("nm", f"Complete defined export table cross-checked against binding/visibility in readelf: {path}", exports)
        return elf


def parse_metadata(path, text):
    def field(name):
        match = re.search(r"^\s*" + re.escape(name) + r":\s*(.+)$", text, re.M)
        if not match:
            raise ValueError(f"Missing ELF field {name}: {path}")
        return match[1].strip()
    count = int(field("Number of program headers"))
    segment_rows = re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s+0x[0-9a-f]+\s+0x", text, re.M)
    if count != len(segment_rows):
        raise ValueError(f"Incomplete/unrecognized program headers: {path}")
    interp = re.findall(r"\[Requesting program interpreter: (.+)\]", text)
    if segment_rows.count("INTERP") != len(interp) or len(interp) > 1:
        raise ValueError(f"Unrecognized PT_INTERP: {path}")
    dynamic_rows = re.findall(r"^\s*0x[0-9a-f]+\s+\(([^)]+)\)", text, re.M)
    dynamic_count = re.search(r"Dynamic section at offset .* contains (\d+) entries:", text)
    if dynamic_count:
        if int(dynamic_count[1]) != len(dynamic_rows) or not dynamic_rows or dynamic_rows[-1] != "NULL":
            raise ValueError(f"Incomplete dynamic section: {path}")
    elif "There is no dynamic section in this file." not in text:
        raise ValueError(f"Unrecognized dynamic section: {path}")
    if ("DYNAMIC" in segment_rows) != bool(dynamic_count):
        raise ValueError(f"Inconsistent PT_DYNAMIC/section: {path}")
    needed = re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", text)
    if len(needed) != dynamic_rows.count("NEEDED"):
        raise ValueError(f"Unrecognized DT_NEEDED: {path}")
    return Elf(path, field("Type").split()[0], field("Class"), field("Machine"),
               interp[0] if interp else None, "DYNAMIC" in segment_rows, needed,
               bool(re.search(r"BIND_NOW|\(FLAGS_1\).*\bNOW\b", text)))


def split_version(raw):
    match = re.fullmatch(r"([^@\s]+)(?:@@?([^@\s]+))?", raw)
    if not match:
        raise ValueError(f"Unrecognized dynamic symbol decoration: {raw}")
    return match[1], match[2]


def parse_symbols(text, *, allow_empty=False):
    if allow_empty and not text.strip():
        return []
    header = re.search(r"Symbol table '\.dynsym' contains (\d+) entries:", text)
    if not header:
        raise ValueError("Missing/unrecognized dynamic symbol table")
    rows = [line for line in text.splitlines() if re.match(r"\s*\d+:", line)]
    if len(rows) != int(header[1]):
        raise ValueError("Truncated dynamic symbol table")
    symbols = []
    for index, line in enumerate(rows):
        row = re.fullmatch(r"\s*(\d+):\s+[0-9a-fA-F]+\s+(?:\d+|0x[0-9a-fA-F]+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+)(?:\s+\(\d+\))?)?\s*", line)
        if not row or int(row[1]) != index:
            raise ValueError("Unrecognized dynamic symbol row")
        binding, visibility, section, raw = row.groups()[1:]
        if raw:
            name, version = split_version(raw)
            symbols.append(Symbol(raw, name, version, binding, visibility, section))
    return symbols


def parse_nm(text):
    result = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        row = re.fullmatch(r"[0-9a-fA-F]+\s+[A-Za-z?]\s+(\S+)", line)
        if not row:
            raise ValueError("Unrecognized GNU nm export row")
        split_version(row[1])
        result.add(row[1])
    return result
