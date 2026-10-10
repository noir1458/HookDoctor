# Sources and evidence scope

- DOCUMENTED_UPSTREAM: [Docker multi-platform builds](https://docs.docker.com/build/building/multi-platform/)
  describes explicit platform selection and emulation on Docker Desktop, including
  its performance limitations. It does not establish our fixture or CLI correctness.
- DOCUMENTED_UPSTREAM: [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)
  documents mounting host source into a container.
- DOCUMENTED_UPSTREAM: [GNU readelf](https://sourceware.org/binutils/docs/binutils/readelf.html)
  documents `--dyn-syms`, wide output, header/program-header/dynamic-section
  inspection and `@`/`@@` version decorations. Comparing undecorated names alone
  does not establish symbol version compatibility.
- Reference supplied by contract: [glibc loader manual](https://man7.org/linux/man-pages/man8/ld.so.8.html).
  Live retrieval timed out on this run; local runtime results are recorded separately.
- Reference supplied by contract: [glibc feature-test macros](https://www.gnu.org/software/libc/manual/html_node/Feature-Test-Macros.html).
  Live retrieval failed on this run; compiler flags are harness inputs, not inferred runtime facts.

REPRODUCED_LOCAL results and VERIFIED_BY_CODE references live in EVIDENCE.md.
HYPOTHESIS: if a workload executes an observed open64 binding to libc while the
requested hook exports only open, that open wrapper cannot intercept that call.
The CLI has no function-entry observer; the controlled harness checks its own
source/argv/markers independently.
