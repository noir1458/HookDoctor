"""Bounded POSIX subprocess capture, shared by collectors and the fixture harness."""
from dataclasses import dataclass
import os
import selectors
import signal
import subprocess
import time


@dataclass
class ProcessResult:
    pid: int
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_limited: bool = False

    @property
    def complete(self):
        return not (self.timed_out or self.output_limited)


def _cleanup(proc):
    # Only this Popen's new session is ever signalled, including pipe-owning children.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        proc.wait()
        return
    until = time.monotonic() + 0.5
    while time.monotonic() < until:
        proc.poll()
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()


def run_bounded(argv, *, env, cwd=None, timeout=5.0, max_bytes=5242880):
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    buffers = [bytearray(), bytearray()]
    timed_out = limited = False
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for index, stream in enumerate((proc.stdout, proc.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            while selector.get_map() or proc.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    capacity = max_bytes - sum(map(len, buffers))
                    data = os.read(key.fd, min(65536, capacity + 1))
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        buffers[key.data].extend(data[:capacity])
                        if len(data) > capacity:
                            limited = True
                            break
                if limited:
                    break
    finally:
        _cleanup(proc)
        proc.stdout.close()
        proc.stderr.close()
    return ProcessResult(proc.pid, proc.returncode, bytes(buffers[0]), bytes(buffers[1]),
                         timed_out, limited)
