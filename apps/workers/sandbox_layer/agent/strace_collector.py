"""Parse the output of strace -f -tt -e trace=all.
Adapted from GPE-Charon/sandbox/backends/linux_docker/strace_collector.py
Only change: import from models (not backends.linux_docker.models).
"""

from __future__ import annotations

import re
from collections import defaultdict

from models import (
    EvasionTells,
    MAX_SYSCALL_ARG_CHARS,
    MAX_SYSCALL_SAMPLE_ARGS,
    SyscallSummary,
)

_LINE_RE = re.compile(
    r"^\s*(\d+)\s+"
    r"\d+:\d+:\d+\.\d+\s+"
    r"(\w+)\("
    r"(.*?)\)"
    r"\s*=\s*(.+)$"
)

SYSCALLS_OF_INTEREST = frozenset({
    "execve", "execveat", "clone", "fork", "vfork",
    "connect", "bind", "accept", "socket",
    "openat", "open", "creat", "unlink", "unlinkat", "rename", "renameat",
    "chmod", "chown", "fchmod", "fchown",
    "mmap", "mprotect", "madvise",
    "ptrace", "kill", "tgkill",
    "write", "read",
    "nanosleep", "clock_nanosleep",
    "setuid", "setgid", "setresuid", "setresgid",
    "prctl",
})

# Syscalls too common to carry signal (libc/ld overhead).
# We keep call_count but clear sample_args to avoid noise.
_NOISE_SYSCALLS: frozenset[str] = frozenset({
    "brk", "mmap", "munmap", "mprotect", "madvise",
    "fstat", "stat", "lstat", "newfstatat",
    "close", "read", "pread64", "preadv", "readv",
    "lseek", "getdents64", "fcntl", "ioctl",
    "futex", "set_robust_list", "get_robust_list",
    "rt_sigaction", "rt_sigprocmask", "rt_sigreturn",
    "gettimeofday", "clock_gettime", "clock_nanosleep",
    "getpid", "getppid", "gettid", "getuid", "getgid",
    "getresuid", "getresgid", "getgroups",
    "arch_prctl", "set_tid_address",
    "sched_getaffinity", "sched_yield",
    "access", "faccessat",
})

# Path prefixes to exclude from sample_args (systematic libc/ld lookups).
_NOISE_PATH_PREFIXES: tuple[str, ...] = (
    "/lib/", "/lib64/", "/usr/lib/",
    "/etc/ld.so", "/proc/self/", "/sys/kernel/",
)

# Systematic UNIX sockets (nscd, dbus, journald).
_NOISE_UNIX_PATHS: frozenset[str] = frozenset({
    "/var/run/nscd/socket",
    "/run/nscd/socket",
    "/run/systemd/journal/socket",
    "/run/dbus/system_bus_socket",
})


def parse_strace_log(log_content: str) -> list[SyscallSummary]:
    counts: dict[str, int] = defaultdict(int)
    pids: dict[str, set[int]] = defaultdict(set)
    args_samples: dict[str, list[str]] = defaultdict(list)

    for line in log_content.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        pid_s, syscall, args_raw, _ = m.groups()
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        counts[syscall] += 1
        pids[syscall].add(pid)
        if syscall not in _NOISE_SYSCALLS and len(args_samples[syscall]) < MAX_SYSCALL_SAMPLE_ARGS:
            arg = args_raw.strip()[:MAX_SYSCALL_ARG_CHARS]
            if (
                arg
                and arg not in args_samples[syscall]
                and arg not in _NOISE_UNIX_PATHS
                and not any(arg.startswith(p) for p in _NOISE_PATH_PREFIXES)
            ):
                args_samples[syscall].append(arg)

    results = [
        SyscallSummary(
            name=sc,
            call_count=cnt,
            unique_pids=sorted(pids[sc]),
            sample_args=args_samples[sc],
        )
        for sc, cnt in counts.items()
    ]
    results.sort(key=lambda s: (s.name not in SYSCALLS_OF_INTEREST, -s.call_count))
    return results


# D1bis — anti-analysis probe tells, matched on the RAW log (before the noise
# filtering in parse_strace_log strips /proc/self/*, arch_prctl and return values).
# Each pattern is something a normal program does not do; the probe IS the tell.
_TRACERPID_RE = re.compile(
    r'\b(?:openat|open)\([^)]*"(?:/proc/self/status|/proc/\d+/status)"'
)
_CONTAINER_RE = re.compile(
    r'\b(?:openat|open|access|faccessat|newfstatat|stat|lstat)\('
    r'[^)]*"(?:/\.dockerenv|/proc/1/cgroup)"'
)
# Excluded as non-discriminating (fire for every process, not just samples):
# rseq->ENOSYS (universal under gVisor) and arch_prctl(0x3001) (issued by the
# benign detonation runtime — Node/PDF.js, recent glibc — confirmed on benign
# PDFs during validation: it inflated every benign score by 0.056).


def extract_evasion_tells(log_content: str) -> EvasionTells:
    """Detect anti-analysis probes in the raw strace log (D1bis).

    See models.signals.EvasionTells for the rationale of each tell.
    """
    return EvasionTells(
        reads_tracerpid=bool(_TRACERPID_RE.search(log_content)),
        container_fingerprint=bool(_CONTAINER_RE.search(log_content)),
    )


def extract_sleep_cumulated(log_content: str) -> float:
    total_ns = 0
    for m in re.finditer(r"nanosleep\(\{tv_sec=(\d+),\s*tv_nsec=(\d+)\}", log_content):
        total_ns += int(m.group(1)) * 1_000_000_000 + int(m.group(2))
    return total_ns / 1_000_000_000
