"""Parse la sortie strace -f -tt -e trace=all.
Adapté de GPE-Charon/sandbox/backends/linux_docker/strace_collector.py
Seule modification : import depuis models (pas backends.linux_docker.models).
"""

from __future__ import annotations

import re
from collections import defaultdict

from models import (
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

# Syscalls trop communs pour apporter un signal (libc/ld overhead).
# On conserve le call_count mais on vide sample_args pour éviter le bruit.
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

# Préfixes de chemins à exclure des sample_args (libc/ld lookups systématiques).
_NOISE_PATH_PREFIXES: tuple[str, ...] = (
    "/lib/", "/lib64/", "/usr/lib/",
    "/etc/ld.so", "/proc/self/", "/sys/kernel/",
)

# Sockets UNIX systématiques (nscd, dbus, journald).
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


def extract_sleep_cumulated(log_content: str) -> float:
    total_ns = 0
    for m in re.finditer(r"nanosleep\(\{tv_sec=(\d+),\s*tv_nsec=(\d+)\}", log_content):
        total_ns += int(m.group(1)) * 1_000_000_000 + int(m.group(2))
    return total_ns / 1_000_000_000
